#!/usr/bin/env bash
# Docker E2E スモークテスト。
#
# docker compose で全サービスを実起動し、nginx(:8080) 経由で
#   ログイン → アップロード → 同期分析 → 非同期分析(Celeryワーカー)
# までの一気通貫を検証する。起動順序・nginx ルーティング・CORS・認証・
# ワーカーといった「結合部」のリグレッションを CI で自動検知するのが目的。
#
# 稼働中の開発スタックを壊さないよう、専用プロジェクト名で隔離して起動する
# （ボリュームも独立。クリーンアップは down -v でこのプロジェクトのみ削除）。
# ※ ホストポート 8080 は共有のため、既存スタックが起動中だと衝突する。
#   その場合は先に `docker compose down` してから実行すること。
set -euo pipefail

cd "$(dirname "$0")/.."

PROJECT="pivexa-e2e"
BASE="http://localhost:8080"
COOKIE="$(mktemp)"
COMPOSE=(docker compose -p "$PROJECT")

log()  { printf '\n\033[1;34m== %s\033[0m\n' "$*"; }
fail() { printf '\033[1;31mFAIL: %s\033[0m\n' "$*" >&2; exit 1; }

cleanup() {
  log "クリーンアップ (down -v)"
  "${COMPOSE[@]}" down -v --remove-orphans >/dev/null 2>&1 || true
  rm -f "$COOKIE"
}
trap cleanup EXIT

# --- .env を用意（CI には存在しないため生成） -------------------------------
if [ ! -f .env ]; then
  log ".env を .env.example から生成"
  sed -e "s|^JWT_SECRET=.*|JWT_SECRET=e2e-ci-$(date +%s)-secret|" \
      -e "s|^ADMIN_PASSWORD=.*|ADMIN_PASSWORD=e2e-admin-pass|" \
      .env.example > .env
fi
ADMIN_USER="$(grep -E '^ADMIN_USER=' .env | cut -d= -f2-)"
ADMIN_PASSWORD="$(grep -E '^ADMIN_PASSWORD=' .env | cut -d= -f2-)"

# --- 起動 -------------------------------------------------------------------
log "docker compose up -d --build"
"${COMPOSE[@]}" up -d --build

log "API ヘルスチェック待機 (最大 120s)"
for i in $(seq 1 60); do
  if curl -sf "$BASE/api/health" >/dev/null 2>&1; then
    echo "healthy (${i}回目)"; break
  fi
  [ "$i" = 60 ] && { "${COMPOSE[@]}" logs --tail=50; fail "API が起動しませんでした"; }
  sleep 2
done

# --- ログイン ---------------------------------------------------------------
log "ログイン"
code=$(curl -s -o /dev/null -w '%{http_code}' -c "$COOKIE" -X POST "$BASE/api/auth/login" \
  -H 'Content-Type: application/json' \
  -d "{\"username\":\"$ADMIN_USER\",\"password\":\"$ADMIN_PASSWORD\"}")
[ "$code" = 200 ] || fail "ログイン失敗 (HTTP $code)"
echo "ログイン OK"

# --- アップロード -----------------------------------------------------------
log "CSV アップロード"
CSV="$(mktemp --suffix=.csv)"
python3 - "$CSV" <<'PY'
import sys
with open(sys.argv[1], "w") as f:
    f.write("x1,x2,y\n")
    for i in range(60):
        x1, x2 = 10 + i, (i % 7) * 3
        y = 2 * x1 + x2 + (i % 5)
        f.write(f"{x1},{x2},{y}\n")
PY
up=$(curl -s -b "$COOKIE" -X POST "$BASE/api/datasets" -F "file=@$CSV")
rm -f "$CSV"
dataset_id=$(printf '%s' "$up" | python3 -c 'import sys,json; print(json.load(sys.stdin)["id"])') \
  || fail "アップロード応答が不正: $up"
echo "dataset_id=$dataset_id ($up)"

# --- 同期分析 (descriptive: 即時 done) --------------------------------------
log "同期分析 (descriptive)"
job=$(curl -s -b "$COOKIE" -X POST "$BASE/api/jobs" -H 'Content-Type: application/json' \
  -d "{\"dataset_id\":$dataset_id,\"method\":\"descriptive\",\"config\":{\"explanatory\":[\"x1\",\"x2\",\"y\"]}}")
status=$(printf '%s' "$job" | python3 -c 'import sys,json; print(json.load(sys.stdin)["status"])')
[ "$status" = "done" ] || fail "同期分析が done になりません: $job"
echo "同期分析 OK ($job)"

# --- 非同期分析 (linear_regression: Celery ワーカー経由) --------------------
log "非同期分析 (linear_regression / ワーカー)"
job=$(curl -s -b "$COOKIE" -X POST "$BASE/api/jobs" -H 'Content-Type: application/json' \
  -d "{\"dataset_id\":$dataset_id,\"method\":\"linear_regression\",\"config\":{\"target\":\"y\",\"explanatory\":[\"x1\",\"x2\"]}}")
job_id=$(printf '%s' "$job" | python3 -c 'import sys,json; print(json.load(sys.stdin)["job_id"])') \
  || fail "ジョブ作成失敗: $job"
echo "job_id=$job_id を投入、完了をポーリング"

result_id=""
for i in $(seq 1 30); do
  jr=$(curl -s -b "$COOKIE" "$BASE/api/jobs/$job_id")
  st=$(printf '%s' "$jr" | python3 -c 'import sys,json; print(json.load(sys.stdin)["status"])')
  echo "  [$i] status=$st"
  if [ "$st" = "done" ]; then
    result_id=$(printf '%s' "$jr" | python3 -c 'import sys,json; print(json.load(sys.stdin)["result_id"])')
    break
  fi
  [ "$st" = "error" ] && { "${COMPOSE[@]}" logs --tail=50 worker; fail "ワーカーがエラー: $jr"; }
  sleep 2
done
[ -n "$result_id" ] || { "${COMPOSE[@]}" logs --tail=50 worker; fail "ワーカーがタイムアウト"; }

res=$(curl -s -o /dev/null -w '%{http_code}' -b "$COOKIE" "$BASE/api/results/$result_id")
[ "$res" = 200 ] || fail "結果取得失敗 (HTTP $res)"
echo "非同期分析 OK (result_id=$result_id)"

log "E2E スモーク 全項目 PASS ✅"
