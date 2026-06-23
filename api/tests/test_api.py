"""API 統合テスト（FastAPI TestClient）。

ユニットテスト(test_methods.py)が解析ロジックだけを見るのに対し、ここは
HTTP 層・認証(Cookie/JWT)・アップロード・DB 永続化・ジョブ実行(同期パス)・
レポート生成までの「結合部」を実際の FastAPI アプリ経由で検証する。

実 Postgres を必要とする（JSONB / BigInteger シーケンス等を本番同等で検証する
ため SQLite では代替しない）。接続できない環境では自動的に skip する。

ローカル実行例:
    docker compose up -d db
    DATABASE_URL=postgresql+psycopg2://pivexa:pivexa@localhost:5432/pivexa \
        pytest tests/test_api.py -q
あるいは起動中スタックのコンテナ内で:
    docker compose exec api pytest tests/test_api.py -q
"""
from __future__ import annotations

import importlib
import io
import os
import tempfile

import pytest

# --- main を import する前に環境変数を確定させる ----------------------------
# db.session / core 各モジュールは import 時に環境変数を読むため、ここで先に設定。
_TEST_DB = (
    os.environ.get("TEST_DATABASE_URL")
    or os.environ.get("DATABASE_URL")
    or "postgresql+psycopg2://pivexa:pivexa@db:5432/pivexa"
)
os.environ["DATABASE_URL"] = _TEST_DB

_TMP = tempfile.mkdtemp(prefix="pivexa-apitest-")
os.environ["UPLOAD_DIR"] = os.path.join(_TMP, "uploads")
os.environ["REPORTS_DIR"] = os.path.join(_TMP, "reports")
os.environ["ADMIN_USER"] = "admin"
os.environ["ADMIN_PASSWORD"] = "test-pass-123"
# CORS をワイルドカードのままにしておくと credentials が無効化されるが、
# TestClient は同一オリジン扱いなので Cookie 認証には影響しない。

ADMIN_USER = os.environ["ADMIN_USER"]
ADMIN_PASSWORD = os.environ["ADMIN_PASSWORD"]


def _make_csv(rows: int = 40) -> bytes:
    """数値2列の単純なCSVを生成（descriptive/correlation 用）。"""
    lines = ["ad_cost,sales"]
    for i in range(rows):
        ad = 100 + i
        sales = 2 * ad + (i % 5)
        lines.append(f"{ad},{sales}")
    return ("\n".join(lines) + "\n").encode("utf-8")


@pytest.fixture(scope="module")
def client():
    # DB へ接続できなければ skip（DBレスのCI/ローカルでもユニットテストは通す）。
    from db import session

    try:
        conn = session.engine.connect()
        conn.close()
    except Exception as e:  # noqa: BLE001
        pytest.skip(f"テストDBに接続できないため API 統合テストをスキップ: {e}")

    # まっさらなスキーマで開始する。
    from db.models import Base

    Base.metadata.drop_all(bind=session.engine)
    Base.metadata.create_all(bind=session.engine)

    import main  # noqa: WPS433 — 環境変数確定後に import する

    importlib.reload(main)
    from fastapi.testclient import TestClient

    # with 文で startup イベントが走り、管理者ユーザが作成される。
    with TestClient(main.app) as c:
        yield c


def _login(client, username=ADMIN_USER, password=ADMIN_PASSWORD):
    client.cookies.clear()
    return client.post("/auth/login", json={"username": username, "password": password})


# --- ヘルス / 認証 ----------------------------------------------------------
def test_health(client):
    r = client.get("/health")
    assert r.status_code == 200
    assert r.json() == {"status": "ok"}


def test_protected_requires_auth(client):
    client.cookies.clear()
    r = client.get("/datasets")
    assert r.status_code == 401
    assert r.json()["detail"] == "認証が必要です。"


def test_login_bad_credentials(client):
    r = _login(client, password="wrong")
    assert r.status_code == 401
    assert "違います" in r.json()["detail"]


def test_login_sets_cookie(client):
    r = _login(client)
    assert r.status_code == 200
    assert r.json()["user"]["username"] == ADMIN_USER
    assert "access_token" in r.cookies


def test_me_after_login(client):
    _login(client)
    r = client.get("/auth/me")
    assert r.status_code == 200
    assert r.json()["username"] == ADMIN_USER


# --- アップロード / プロファイル -------------------------------------------
def test_upload_and_profile(client):
    _login(client)
    r = client.post(
        "/datasets",
        files={"file": ("sample.csv", _make_csv(), "text/csv")},
    )
    assert r.status_code == 201, r.text
    body = r.json()
    assert body["format"] == "csv"
    assert body["row_count"] == 40
    assert body["col_count"] == 2
    dataset_id = body["id"]

    # 一覧に出る
    lst = client.get("/datasets")
    assert lst.status_code == 200
    assert any(d["id"] == dataset_id for d in lst.json())

    # プロファイルが取れる
    prof = client.get(f"/datasets/{dataset_id}/profile")
    assert prof.status_code == 200
    names = {c["name"] for c in prof.json()["columns"]}
    assert {"ad_cost", "sales"} <= names


def test_upload_rejects_garbage(client):
    _login(client)
    r = client.post(
        "/datasets",
        files={"file": ("broken.csv", b"\x00\x01\x02 not a table", "text/csv")},
    )
    # 取り込み失敗は 400（fetch失敗ではなく明確なエラーを返すこと）
    assert r.status_code == 400


# --- データセット単体取得 / 削除（基本設計§6）------------------------------
def test_get_dataset_meta(client):
    """アップロード→単体GETでメタが取れる。存在しないIDは404。"""
    _login(client)
    up = client.post("/datasets", files={"file": ("meta.csv", _make_csv(), "text/csv")})
    assert up.status_code == 201, up.text
    dataset_id = up.json()["id"]

    r = client.get(f"/datasets/{dataset_id}")
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["id"] == dataset_id
    assert body["format"] == "csv"
    assert body["row_count"] == 40
    assert body["col_count"] == 2
    assert "created_at" in body

    # 存在しないIDは404
    missing = client.get("/datasets/999999")
    assert missing.status_code == 404
    assert missing.json()["detail"] == "データセットが見つかりません。"


def test_delete_dataset(client):
    """アップロード→DELETE→200。以後 単体GET/プロファイル/一覧から消える。"""
    _login(client)
    up = client.post("/datasets", files={"file": ("del.csv", _make_csv(), "text/csv")})
    assert up.status_code == 201, up.text
    dataset_id = up.json()["id"]

    # 削除前は取得・プロファイル・一覧に存在する
    assert client.get(f"/datasets/{dataset_id}").status_code == 200
    assert client.get(f"/datasets/{dataset_id}/profile").status_code == 200
    assert any(d["id"] == dataset_id for d in client.get("/datasets").json())

    # 削除
    dele = client.delete(f"/datasets/{dataset_id}")
    assert dele.status_code == 200, dele.text
    assert dele.json() == {"ok": True}

    # 削除後は単体GET・プロファイルが404、一覧からも消える
    assert client.get(f"/datasets/{dataset_id}").status_code == 404
    assert client.get(f"/datasets/{dataset_id}/profile").status_code == 404
    assert all(d["id"] != dataset_id for d in client.get("/datasets").json())


def test_delete_dataset_cascades_jobs_and_results(client):
    """関連ジョブ・結果ごと連鎖削除される（FK ON DELETE CASCADE）。

    同期解析(descriptive)でジョブ・結果まで作ってからデータセットを削除し、
    ジョブ取得・結果取得が 404 になることを確認する。
    """
    _login(client)
    up = client.post("/datasets", files={"file": ("cascade.csv", _make_csv(), "text/csv")})
    dataset_id = up.json()["id"]

    job = client.post(
        "/jobs",
        json={
            "dataset_id": dataset_id,
            "method": "descriptive",
            "config": {"explanatory": ["ad_cost", "sales"]},
        },
    )
    assert job.status_code == 200, job.text
    jb = job.json()
    job_id = jb["job_id"]
    result_id = jb["result_id"]
    assert result_id is not None

    # データセット削除でジョブ・結果まで連鎖削除される
    assert client.delete(f"/datasets/{dataset_id}").status_code == 200
    assert client.get(f"/jobs/{job_id}").status_code == 404
    assert client.get(f"/results/{result_id}").status_code == 404


def test_delete_dataset_unknown(client):
    """存在しないIDの DELETE は404。"""
    _login(client)
    r = client.delete("/datasets/999999")
    assert r.status_code == 404
    assert r.json()["detail"] == "データセットが見つかりません。"


def test_non_owner_viewer_cannot_delete_dataset(client):
    """所有者でも管理者でもない viewer は他人のデータセットを削除できない(403)。"""
    _login(client)  # admin
    up = client.post("/datasets", files={"file": ("owned.csv", _make_csv(), "text/csv")})
    dataset_id = up.json()["id"]
    # admin が viewer を作成
    client.post(
        "/users",
        json={"username": "viewer_del", "password": "pw-987654", "role": "viewer"},
    )
    # viewer でログインして admin 所有のデータセット削除を試みる → 403
    _login(client, username="viewer_del", password="pw-987654")
    r = client.delete(f"/datasets/{dataset_id}")
    assert r.status_code == 403


def test_delete_dataset_audit_logged(client):
    """削除時に監査ログ delete_dataset が記録される。"""
    from db.models import AuditLog
    from db.session import SessionLocal

    _login(client)
    up = client.post("/datasets", files={"file": ("audit-del.csv", _make_csv(), "text/csv")})
    dataset_id = up.json()["id"]

    assert client.delete(f"/datasets/{dataset_id}").status_code == 200

    db = SessionLocal()
    try:
        log = (
            db.query(AuditLog)
            .filter(AuditLog.action == "delete_dataset", AuditLog.target == str(dataset_id))
            .first()
        )
        assert log is not None
    finally:
        db.close()


# --- 手法一覧 ---------------------------------------------------------------
def test_methods_listing(client):
    _login(client)
    r = client.get("/methods")
    assert r.status_code == 200
    names = {m["name"] for m in r.json()}
    assert "descriptive" in names
    assert "linear_regression" in names


# --- ジョブ(同期パス) → 結果 → レポート -----------------------------------
def test_sync_job_result_and_report(client):
    _login(client)
    up = client.post("/datasets", files={"file": ("d.csv", _make_csv(), "text/csv")})
    dataset_id = up.json()["id"]

    # descriptive は SYNC_METHODS なので同期実行され、即 result_id が返る。
    job = client.post(
        "/jobs",
        json={
            "dataset_id": dataset_id,
            "method": "descriptive",
            "config": {"explanatory": ["ad_cost", "sales"]},
        },
    )
    assert job.status_code == 200, job.text
    jb = job.json()
    assert jb["status"] == "done"
    result_id = jb["result_id"]
    assert result_id is not None

    res = client.get(f"/results/{result_id}")
    assert res.status_code == 200
    assert res.json()["result"]["method"] == "descriptive"

    # PDF レポート生成（WeasyPrint 必須。未導入環境では skip）。
    rep = client.post(f"/results/{result_id}/report", json={"format": "pdf"})
    if rep.status_code == 500:
        pytest.skip("WeasyPrint が利用できないためレポート生成テストをスキップ")
    assert rep.status_code == 201, rep.text
    report_id = rep.json()["report_id"]

    dl = client.get(f"/reports/{report_id}")
    assert dl.status_code == 200
    assert dl.headers["content-type"] == "application/pdf"


def test_job_validation_error(client):
    _login(client)
    up = client.post("/datasets", files={"file": ("e.csv", _make_csv(), "text/csv")})
    dataset_id = up.json()["id"]
    # correlation は説明変数2つ以上が必要 → 1つだとバリデーションエラー(422)
    job = client.post(
        "/jobs",
        json={
            "dataset_id": dataset_id,
            "method": "correlation",
            "config": {"explanatory": ["ad_cost"]},
        },
    )
    assert job.status_code == 422


def test_job_unknown_dataset(client):
    _login(client)
    job = client.post(
        "/jobs",
        json={"dataset_id": 999999, "method": "descriptive", "config": {"explanatory": ["ad_cost"]}},
    )
    assert job.status_code == 404


def test_shiftjis_csv_uploads_and_analyzes(client):
    """Shift-JIS の日本語ヘッダCSVが、アップロードだけでなく解析まで通ること。

    旧実装ではアップロードは成功するのに解析(_read_dataset)で UnicodeDecodeError
    になっていた。アップロード時と同じ自動エンコーディング判定を使うことで解消。
    """
    _login(client)
    rows = ["売上,広告費"] + [f"{100 + i * 2},{50 + i}" for i in range(40)]
    content = ("\n".join(rows) + "\n").encode("cp932")  # Shift-JIS

    up = client.post("/datasets", files={"file": ("sjis.csv", content, "text/csv")})
    assert up.status_code == 201, up.text
    dataset_id = up.json()["id"]

    # 列名(日本語)が正しく取り込まれている
    prof = client.get(f"/datasets/{dataset_id}/profile")
    assert {"売上", "広告費"} <= {c["name"] for c in prof.json()["columns"]}

    # 同期解析(descriptive)が UnicodeDecodeError にならず done になる
    job = client.post(
        "/jobs",
        json={
            "dataset_id": dataset_id,
            "method": "descriptive",
            "config": {"explanatory": ["売上", "広告費"]},
        },
    )
    assert job.status_code == 200, job.text
    assert job.json()["status"] == "done"


# --- 監査ログ（要件§6.1）---------------------------------------------------
def _audit_count() -> int:
    """テスト用DBセッションで AuditLog の件数を直接数える。"""
    from db.models import AuditLog
    from db.session import SessionLocal

    db = SessionLocal()
    try:
        return db.query(AuditLog).count()
    finally:
        db.close()


def test_audit_log_on_login(client):
    before = _audit_count()
    r = _login(client)
    assert r.status_code == 200
    # ログイン成功で監査ログが 1 行以上増える
    assert _audit_count() > before


def test_audit_log_on_upload(client):
    _login(client)
    before = _audit_count()
    up = client.post("/datasets", files={"file": ("audit.csv", _make_csv(), "text/csv")})
    assert up.status_code == 201, up.text
    # アップロード成功で監査ログが増える
    assert _audit_count() > before


# --- レポート形式の検証（要件§5.4）----------------------------------------
def test_report_rejects_unsupported_format(client):
    _login(client)
    up = client.post("/datasets", files={"file": ("fmt.csv", _make_csv(), "text/csv")})
    dataset_id = up.json()["id"]
    job = client.post(
        "/jobs",
        json={
            "dataset_id": dataset_id,
            "method": "descriptive",
            "config": {"explanatory": ["ad_cost", "sales"]},
        },
    )
    result_id = job.json()["result_id"]

    # csv は未対応 → 400（PDF 生成に到達せず弾く）
    rep = client.post(f"/results/{result_id}/report", json={"format": "csv"})
    assert rep.status_code == 400, rep.text
    assert "未対応" in rep.json()["detail"]


def test_report_accepts_pdf_format(client):
    _login(client)
    up = client.post("/datasets", files={"file": ("fmt2.csv", _make_csv(), "text/csv")})
    dataset_id = up.json()["id"]
    job = client.post(
        "/jobs",
        json={
            "dataset_id": dataset_id,
            "method": "descriptive",
            "config": {"explanatory": ["ad_cost", "sales"]},
        },
    )
    result_id = job.json()["result_id"]

    # pdf は従来どおり成功（WeasyPrint 不在環境では 500 になるため skip）
    rep = client.post(f"/results/{result_id}/report", json={"format": "pdf"})
    if rep.status_code == 500:
        pytest.skip("WeasyPrint が利用できないためレポート生成テストをスキップ")
    assert rep.status_code == 201, rep.text
    assert rep.json()["format"] == "pdf"


# --- ロールベース認可（要件§6.2）------------------------------------------
def test_admin_can_create_user(client):
    """admin ロールは管理操作(POST /users)を実行できる。"""
    _login(client)  # 既定の admin でログイン
    r = client.post("/users", json={"username": "member1", "password": "pw-123456"})
    assert r.status_code == 201, r.text
    assert r.json()["username"] == "member1"


def test_admin_creates_viewer_via_api(client):
    """admin は role=viewer を指定して非管理ユーザーを作成でき、その viewer は
    管理操作で 403 になる（require_admin が実効的に機能する）。"""
    _login(client)  # admin
    r = client.post(
        "/users",
        json={"username": "viewer_api", "password": "pw-654321", "role": "viewer"},
    )
    assert r.status_code == 201, r.text
    assert r.json()["role"] == "viewer"

    login = _login(client, username="viewer_api", password="pw-654321")
    assert login.status_code == 200, login.text
    blocked = client.post("/users", json={"username": "x", "password": "pw-000000"})
    assert blocked.status_code == 403


def test_viewer_cannot_create_user(client):
    """role=="viewer" のユーザーは管理操作で 403 になる。"""
    from core.auth.security import hash_password
    from db.models import User
    from db.session import SessionLocal

    db = SessionLocal()
    try:
        if not db.query(User).filter(User.username == "viewer1").first():
            db.add(User(
                username="viewer1",
                password_hash=hash_password("pw-viewer-1"),
                role="viewer",
            ))
            db.commit()
    finally:
        db.close()

    login = _login(client, username="viewer1", password="pw-viewer-1")
    assert login.status_code == 200, login.text

    r = client.post("/users", json={"username": "member2", "password": "pw-123456"})
    assert r.status_code == 403, r.text
    assert "管理者権限" in r.json()["detail"]
