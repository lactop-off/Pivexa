# Pivexa — 統計解析ツール

データをアップロードし、設定と「実行」だけで統計解析（回帰分析ほか）を行える、
非専門家向けの汎用統計解析ツール。MVP は**オンプレミス単独版（Docker Compose / フリー）**。

設計文書は [`docs/`](./docs) を参照。

| 文書 | 内容 |
|---|---|
| `docs/01_要件定義書.md` | 要件定義（v0.2 確定） |
| `docs/02_基本設計書.md` | システム構成・モジュール・画面・DB・API |
| `docs/03_詳細設計書_共通基盤編.md` | 分析フレーム契約・DB物理スキーマ・API I/O |
| `docs/04_詳細設計書_個別手法編.md` | 標準セット7手法の仕様 |

## アーキテクチャ

```
nginx ─┬─ frontend (Next.js)
       └─ api (FastAPI) ── worker (Celery)
                │              │
              PostgreSQL     Redis
```

解析の中核は「**共通分析フレーム ＋ 個別手法プラグイン**」。全手法は
`api/analysis/base.py` の `AnalysisMethod`（`config_schema / validate / run / interpret`）
を実装し、`registry` に登録する。新手法の追加は `api/analysis/methods/` に
1ファイル足すだけ（フロント・API・ジョブ基盤の変更不要）。

## 標準セット（MVP・7手法）

記述統計 / 相関分析 / クロス集計＋カイ二乗 / t検定 / 分散分析(ANOVA) /
重回帰分析 / ロジスティック回帰

## 起動（Docker Compose）

```bash
cp .env.example .env   # 値を編集（管理者パスワード・JWT_SECRET など）
docker compose up --build
# ブラウザで http://localhost:8080
```

初回起動時、`.env` の `ADMIN_USER` / `ADMIN_PASSWORD` で管理者が作成されます。

## 開発・テスト（API）

```bash
cd api
python -m venv .venv && . .venv/bin/activate
pip install -r requirements.txt
pytest                # 分析フレーム＋7手法のスモークテスト
```

## ディレクトリ

```
api/
  analysis/      # 分析フレーム（base/registry/schema/interpret/charts）＋ methods/（7手法）
  core/          # auth / dataset(取り込み・プロファイリング) ほか
  db/            # SQLAlchemy モデル・セッション
  tasks/         # Celery（ジョブ実行）
  main.py        # FastAPI エンドポイント
frontend/        # Next.js（MVP スケルトン）
nginx/           # リバースプロキシ
docs/            # 要件定義・基本設計・詳細設計
```

## 画面（実装済み）

| ID | 画面 | ルート |
|---|---|---|
| S-01 | ログイン | `/login` |
| S-02/03 | データセット一覧・アップロード | `/` |
| S-04 | プロファイル・前処理 | `/datasets/[id]/profile` |
| S-05〜08 | 分析設定・実行・結果・解釈 | `/datasets/[id]/analyze` |
| S-07/08 | 結果（リンク用） | `/results/[id]` |
| S-09 | レポート出力 | 結果画面の「PDF / 印刷で出力」 |
| S-10 | ユーザー管理 | `/users` |

非同期ジョブはフロントがポーリングで完了を待ち、結果・解釈・グラフ・有意性の
見える化を手法非依存に描画する（共通スキーマに準拠）。

## 現状と今後

- ✅ 分析フレーム＋7手法（テスト通過）、取り込み・プロファイリング、認証、ジョブ基盤、API、Docker 構成
- ✅ フロントエンド本実装（画面 S-01〜S-10、ビルド通過）
- 🚧 レポート PDF 生成はブラウザ印刷（`window.print`）。サーバ側 WeasyPrint 出力は今後
- 🚧 Alembic マイグレーション（現状は起動時 `create_all`）
- 後フェーズ: 多変量解析・時系列、クラウド/マルチテナント SaaS・課金
