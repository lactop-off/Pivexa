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
