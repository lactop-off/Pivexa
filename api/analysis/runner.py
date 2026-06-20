"""解析実行のオーケストレーション。

前処理の適用 → 手法の validate → run → interpret を共通化する。
ジョブ基盤（同期/Celery）から呼び出される単一の入口。
"""
from __future__ import annotations

import pandas as pd

from .base import DatasetProfile
from .registry import get_method
from .schema import AnalysisConfig, AnalysisResult, Interpretation, ValidationResult


def apply_preprocessing(df: pd.DataFrame, operations: list[dict]) -> pd.DataFrame:
    """前処理設定（共通基盤編 5.2）を DataFrame に非破壊で適用する。"""
    out = df.copy()
    for op in operations or []:
        t = op.get("type")
        col = op.get("column")
        if t == "impute":
            if col not in out.columns:
                continue
            method = op.get("method", "median")
            if method == "median" and pd.api.types.is_numeric_dtype(out[col]):
                out[col] = out[col].fillna(out[col].median())
            elif method == "mean" and pd.api.types.is_numeric_dtype(out[col]):
                out[col] = out[col].fillna(out[col].mean())
            elif method == "mode":
                mode = out[col].mode()
                if not mode.empty:
                    out[col] = out[col].fillna(mode.iloc[0])
            elif method == "missing_category":
                out[col] = out[col].fillna("欠損")
        elif t == "drop_column":
            out = out.drop(columns=[col], errors="ignore")
        elif t == "cast":
            to = op.get("to")
            if to == "numeric":
                out[col] = pd.to_numeric(out[col], errors="coerce")
            elif to == "categorical":
                out[col] = out[col].astype("string")
    return out


def validate(config: AnalysisConfig, df: pd.DataFrame) -> ValidationResult:
    method = get_method(config.method)
    profile = DatasetProfile.from_dataframe(df)
    return method.validate(config, profile)


def run_analysis(
    config: AnalysisConfig,
    df: pd.DataFrame,
    operations: list[dict] | None = None,
) -> tuple[AnalysisResult, Interpretation]:
    """前処理適用後に解析を実行し、結果と解釈を返す。"""
    method = get_method(config.method)
    processed = apply_preprocessing(df, operations or [])
    result = method.run(config, processed)
    interpretation = method.interpret(result)
    return result, interpretation
