"""Celery アプリ定義（詳細設計書 共通基盤編 1.4, 5.3）。"""
from __future__ import annotations

import os

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
