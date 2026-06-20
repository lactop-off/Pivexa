"""Celery アプリ定義（詳細設計書 共通基盤編 1.4, 5.3）。"""
from __future__ import annotations

import os
import sys

# Celery の fork プールワーカーには cwd が sys.path に入らないため、api ルートを
# 明示的に追加する（`from db.models import ...` 等の絶対 import を解決するため）。
_API_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _API_ROOT not in sys.path:
    sys.path.insert(0, _API_ROOT)

from celery import Celery

REDIS_URL = os.environ.get("REDIS_URL", "redis://redis:6379/0")

celery_app = Celery("pivexa", broker=REDIS_URL, backend=REDIS_URL)
celery_app.conf.update(
    task_serializer="json",
    result_serializer="json",
    accept_content=["json"],
    task_track_started=True,
    include=["tasks.jobs"],  # worker 起動時に tasks.jobs を読み込みタスクを登録
)
