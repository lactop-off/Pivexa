"""FastAPI アプリ（詳細設計書 共通基盤編 7 の API I/O に対応）。"""
from __future__ import annotations

import os
import uuid
from datetime import datetime, timezone

import pandas as pd
from fastapi import Depends, FastAPI, File, HTTPException, Request, Response, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from sqlalchemy.orm import Session

from analysis import get_method, list_methods
from analysis.base import DatasetProfile
from analysis.registry import UnknownMethodError
from analysis.schema import AnalysisConfig
from core.auth.security import (
    create_access_token,
    decode_token,
    hash_password,
    verify_password,
)
from core.dataset import profiling
from db.models import (
    AnalysisJob,
    AnalysisResultRow,
    Dataset,
    DatasetColumn,
    Preprocessing,
    User,
)
from db.session import get_db, init_db
from tasks.jobs import execute_job, execute_job_task

UPLOAD_DIR = os.environ.get("UPLOAD_DIR", "/data/uploads")
SYNC_ROW_THRESHOLD = 10_000
SYNC_METHODS = {"descriptive", "correlation"}

app = FastAPI(title="Pivexa 統計解析ツール API")
app.add_middleware(
    CORSMiddleware,
    allow_origins=os.environ.get("CORS_ORIGINS", "*").split(","),
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.on_event("startup")
def _startup() -> None:
    os.makedirs(UPLOAD_DIR, exist_ok=True)
    try:
        init_db()
        _ensure_admin()
    except Exception:  # noqa: BLE001
        # DB 未起動でもアプリ自体は立ち上げる（ヘルスチェック用）
        pass


def _ensure_admin() -> None:
    from db.session import SessionLocal

    db = SessionLocal()
    try:
        if db.query(User).count() == 0:
            db.add(User(
                username=os.environ.get("ADMIN_USER", "admin"),
                password_hash=hash_password(os.environ.get("ADMIN_PASSWORD", "admin")),
                role="admin",
            ))
            db.commit()
    finally:
        db.close()


# --- 認証 -------------------------------------------------------------------
def current_user(request: Request, db: Session = Depends(get_db)) -> User:
    token = request.cookies.get("access_token")
    if not token:
        raise HTTPException(status_code=401, detail="認証が必要です。")
    payload = decode_token(token)
    if not payload:
        raise HTTPException(status_code=401, detail="セッションが無効です。")
    user = db.query(User).filter(User.username == payload["sub"]).first()
    if not user:
        raise HTTPException(status_code=401, detail="ユーザーが存在しません。")
    return user


class LoginReq(BaseModel):
    username: str
    password: str


@app.post("/auth/login")
def login(body: LoginReq, response: Response, db: Session = Depends(get_db)):
    user = db.query(User).filter(User.username == body.username).first()
    if not user or not verify_password(body.password, user.password_hash):
        raise HTTPException(status_code=401, detail="ユーザー名またはパスワードが違います。")
    token = create_access_token(user.username, user.role)
    response.set_cookie("access_token", token, httponly=True, samesite="lax")
    return {"user": {"id": user.id, "username": user.username, "role": user.role}}


@app.post("/auth/logout")
def logout(response: Response):
    response.delete_cookie("access_token")
    return {"ok": True}


@app.get("/health")
def health():
    return {"status": "ok"}


# --- データセット -----------------------------------------------------------
@app.post("/datasets", status_code=201)
async def upload_dataset(
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
    user: User = Depends(current_user),
):
    content = await file.read()
    try:
        df, fmt = profiling.read_table(content, file.filename or "upload.csv")
    except profiling.IngestError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e

    os.makedirs(UPLOAD_DIR, exist_ok=True)
    path = os.path.join(UPLOAD_DIR, f"{uuid.uuid4().hex}_{file.filename}")
    with open(path, "wb") as f:
        f.write(content)

    ds = Dataset(
        name=file.filename or "dataset",
        original_name=file.filename or "dataset",
        format=fmt,
        row_count=len(df),
        col_count=df.shape[1],
        file_path=path,
        created_by=user.id,
    )
    db.add(ds)
    db.flush()

    for col in profiling.profile(df):
        db.add(DatasetColumn(
            dataset_id=ds.id, name=col["name"], inferred_type=col["type"],
            missing_count=col["missing"], summary={**col["summary"], "recommendation": col["recommendation"]},
        ))
    db.commit()
    return {"id": ds.id, "name": ds.name, "format": fmt, "row_count": len(df), "col_count": df.shape[1]}


@app.get("/datasets")
def list_datasets(db: Session = Depends(get_db), user: User = Depends(current_user)):
    rows = db.query(Dataset).order_by(Dataset.created_at.desc()).all()
    return [{"id": d.id, "name": d.name, "format": d.format,
             "row_count": d.row_count, "col_count": d.col_count} for d in rows]


@app.get("/datasets/{dataset_id}/profile")
def get_profile(dataset_id: int, db: Session = Depends(get_db), user: User = Depends(current_user)):
    cols = db.query(DatasetColumn).filter(DatasetColumn.dataset_id == dataset_id).all()
    if not cols:
        raise HTTPException(status_code=404, detail="データセットが見つかりません。")
    out = []
    for c in cols:
        summary = dict(c.summary or {})
        rec = summary.pop("recommendation", None)
        out.append({"name": c.name, "type": c.inferred_type, "missing": c.missing_count,
                    "summary": summary, "recommendation": rec})
    return {"dataset_id": dataset_id, "columns": out}


class PreprocessReq(BaseModel):
    operations: list[dict]


@app.post("/datasets/{dataset_id}/preprocess")
def set_preprocess(dataset_id: int, body: PreprocessReq,
                   db: Session = Depends(get_db), user: User = Depends(current_user)):
    db.add(Preprocessing(dataset_id=dataset_id, operations={"operations": body.operations}))
    db.commit()
    return {"ok": True}


# --- 手法 -------------------------------------------------------------------
@app.get("/methods")
def methods(db: Session = Depends(get_db), user: User = Depends(current_user)):
    return [{
        "name": m.name, "display_name": m.display_name,
        "needs_target": m.needs_target, "target_kind": m.target_kind, "min_rows": m.min_rows,
    } for m in list_methods()]


@app.get("/datasets/{dataset_id}/methods/{method}/schema")
def method_schema(dataset_id: int, method: str,
                  db: Session = Depends(get_db), user: User = Depends(current_user)):
    cols = db.query(DatasetColumn).filter(DatasetColumn.dataset_id == dataset_id).all()
    if not cols:
        raise HTTPException(status_code=404, detail="データセットが見つかりません。")
    profile = DatasetProfile({c.name: c.inferred_type for c in cols}, _row_count(db, dataset_id))
    try:
        return get_method(method).config_schema(profile).model_dump()
    except UnknownMethodError:
        raise HTTPException(status_code=404, detail="未知の手法です。") from None


# --- ジョブ -----------------------------------------------------------------
class JobReq(BaseModel):
    dataset_id: int
    method: str
    config: dict


@app.post("/jobs")
def create_job(body: JobReq, db: Session = Depends(get_db), user: User = Depends(current_user)):
    dataset = db.get(Dataset, body.dataset_id)
    if not dataset:
        raise HTTPException(status_code=404, detail="データセットが見つかりません。")
    try:
        method = get_method(body.method)
    except UnknownMethodError:
        raise HTTPException(status_code=404, detail="未知の手法です。") from None

    cols = db.query(DatasetColumn).filter(DatasetColumn.dataset_id == body.dataset_id).all()
    profile = DatasetProfile({c.name: c.inferred_type for c in cols}, dataset.row_count or 0)
    config = AnalysisConfig(method=body.method, **{k: v for k, v in body.config.items() if k != "method"})
    vr = method.validate(config, profile)
    if vr.has_error:
        raise HTTPException(status_code=422, detail={"issues": [i.model_dump() for i in vr.issues]})

    job = AnalysisJob(dataset_id=body.dataset_id, method=body.method,
                      config=config.model_dump(), status="queued", created_by=user.id)
    db.add(job)
    db.commit()
    db.refresh(job)

    # 同期実行の閾値判定
    if (dataset.row_count or 0) <= SYNC_ROW_THRESHOLD and body.method in SYNC_METHODS:
        result_id = execute_job(job.id)
        return {"job_id": job.id, "status": "done", "result_id": result_id}

    if execute_job_task is not None:
        execute_job_task.delay(job.id)
        return {"job_id": job.id, "status": "queued", "result_id": None}

    # Celery 不在時は同期フォールバック
    result_id = execute_job(job.id)
    return {"job_id": job.id, "status": "done", "result_id": result_id}


@app.get("/jobs/{job_id}")
def get_job(job_id: int, db: Session = Depends(get_db), user: User = Depends(current_user)):
    job = db.get(AnalysisJob, job_id)
    if not job:
        raise HTTPException(status_code=404, detail="ジョブが見つかりません。")
    result = db.query(AnalysisResultRow).filter(AnalysisResultRow.job_id == job_id).first()
    return {"job_id": job.id, "status": job.status,
            "result_id": result.id if result else None,
            "error_message": job.error_message}


@app.get("/results/{result_id}")
def get_result(result_id: int, db: Session = Depends(get_db), user: User = Depends(current_user)):
    row = db.get(AnalysisResultRow, result_id)
    if not row:
        raise HTTPException(status_code=404, detail="結果が見つかりません。")
    return {"result": row.result, "interpretation": row.interpretation}


def _row_count(db: Session, dataset_id: int) -> int:
    ds = db.get(Dataset, dataset_id)
    return ds.row_count if ds and ds.row_count else 0
