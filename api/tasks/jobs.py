"""解析ジョブの実行（同期/非同期共通のロジック）。"""
from __future__ import annotations

import os
from datetime import datetime, timezone

import pandas as pd

from analysis import charts
from analysis.runner import run_analysis
from analysis.schema import AnalysisConfig
from db.models import AnalysisJob, AnalysisResultRow, Dataset, Preprocessing
from db.session import SessionLocal

REPORTS_DIR = os.environ.get("REPORTS_DIR", "/data/reports")


def execute_job(job_id: int) -> int:
    """ジョブを実行し result_id を返す。Celery タスク・同期実行の双方から呼ばれる。"""
    charts.set_output_dir(REPORTS_DIR)
    db = SessionLocal()
    try:
        job = db.get(AnalysisJob, job_id)
        if job is None:
            raise ValueError(f"job {job_id} not found")
        job.status = "running"
        db.commit()

        dataset = db.get(Dataset, job.dataset_id)
        df = _read_dataset(dataset)
        pre = (
            db.query(Preprocessing)
            .filter(Preprocessing.dataset_id == job.dataset_id)
            .order_by(Preprocessing.created_at.desc())
            .first()
        )
        operations = pre.operations.get("operations", []) if pre else []

        config = AnalysisConfig(**job.config)
        result, interpretation = run_analysis(config, df, operations)

        row = AnalysisResultRow(
            job_id=job.id,
            result=result.model_dump(),
            interpretation=interpretation.model_dump(),
        )
        db.add(row)
        job.status = "done"
        job.finished_at = datetime.now(timezone.utc)
        db.commit()
        db.refresh(row)
        return row.id
    except Exception as e:  # noqa: BLE001
        db.rollback()
        job = db.get(AnalysisJob, job_id)
        if job:
            job.status = "error"
            job.error_message = _user_message(e)
            job.finished_at = datetime.now(timezone.utc)
            db.commit()
        raise
    finally:
        db.close()


def _read_dataset(dataset) -> pd.DataFrame:
    if dataset.format == "excel":
        return pd.read_excel(dataset.file_path)
    return pd.read_csv(dataset.file_path)


def _user_message(e: Exception) -> str:
    return f"解析中にエラーが発生しました: {e}"


# --- Celery タスク ---------------------------------------------------------
try:
    from .celery_app import celery_app

    @celery_app.task(name="execute_job")
    def execute_job_task(job_id: int) -> int:
        return execute_job(job_id)
except Exception:  # noqa: BLE001
    # Celery 未設定環境（テスト等）でも import 可能にする
    execute_job_task = None
