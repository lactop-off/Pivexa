"""データ取り込みと自動プロファイリング（詳細設計書 共通基盤編 5.1）。"""
from __future__ import annotations

import io
import os

import pandas as pd

MAX_UPLOAD_MB = int(os.environ.get("MAX_UPLOAD_MB", "50"))
DROP_MISSING_RATIO = 0.5      # 欠損率がこれを超えたら列削除を推奨
HIGH_CARDINALITY_RATIO = 0.9  # ユニーク率がこれを超える文字列列は ID 的とみなす


class IngestError(ValueError):
    pass


def read_table(content: bytes, filename: str) -> tuple[pd.DataFrame, str]:
    """CSV/Excel を読み込み (DataFrame, format) を返す。

    文字コード・区切り文字は自動判定する。
    """
    if len(content) == 0:
        raise IngestError("ファイルが空です。")
    if len(content) > MAX_UPLOAD_MB * 1024 * 1024:
        raise IngestError(f"ファイルサイズが上限（{MAX_UPLOAD_MB}MB）を超えています。")

    ext = filename.lower().rsplit(".", 1)[-1] if "." in filename else ""
    try:
        if ext in ("xlsx", "xls"):
            df = pd.read_excel(io.BytesIO(content))
            fmt = "excel"
        else:
            encoding = _detect_encoding(content)
            sep = _detect_separator(content, encoding)
            df = pd.read_csv(io.BytesIO(content), encoding=encoding, sep=sep)
            fmt = "csv"
    except Exception as e:  # noqa: BLE001
        raise IngestError(f"ファイルを読み込めませんでした: {e}") from e

    if df.empty or df.shape[1] == 0:
        raise IngestError("データが空、または列がありません。")
    return df, fmt


def _detect_encoding(content: bytes) -> str:
    try:
        from charset_normalizer import from_bytes

        result = from_bytes(content).best()
        return result.encoding if result else "utf-8"
    except Exception:  # noqa: BLE001
        return "utf-8"


def _detect_separator(content: bytes, encoding: str) -> str:
    import csv

    try:
        sample = content[:8192].decode(encoding, errors="ignore")
        dialect = csv.Sniffer().sniff(sample, delimiters=",\t;")
        return dialect.delimiter
    except Exception:  # noqa: BLE001
        return ","


def infer_type(series: pd.Series) -> str:
    """型推定（数値→日付→カテゴリの優先順、変換成功率95%）。"""
    n = len(series.dropna())
    if n == 0:
        return "categorical"
    numeric = pd.to_numeric(series, errors="coerce").notna().sum()
    if numeric / n >= 0.95:
        return "numeric"
    dates = pd.to_datetime(series, errors="coerce").notna().sum()
    if dates / n >= 0.95:
        return "datetime"
    return "categorical"


def profile(df: pd.DataFrame) -> list[dict]:
    """列ごとのプロファイル＋推奨アクションを返す。"""
    n = len(df)
    columns = []
    for col in df.columns:
        s = df[col]
        ctype = infer_type(s)
        missing = int(s.isna().sum())
        missing_ratio = missing / n if n else 0.0
        summary: dict = {}
        if ctype == "numeric":
            num = pd.to_numeric(s, errors="coerce")
            summary = {
                "mean": _f(num.mean()), "min": _f(num.min()), "max": _f(num.max()),
                "p25": _f(num.quantile(0.25)), "p50": _f(num.quantile(0.50)),
                "p75": _f(num.quantile(0.75)),
            }
        else:
            unique_ratio = s.nunique(dropna=True) / n if n else 0.0
            summary = {"unique_ratio": round(unique_ratio, 4), "unique": int(s.nunique(dropna=True))}

        columns.append({
            "name": str(col),
            "type": ctype,
            "missing": missing,
            "summary": summary,
            "recommendation": _recommend(ctype, missing_ratio, summary),
        })
    return columns


def _recommend(ctype: str, missing_ratio: float, summary: dict) -> dict | None:
    if missing_ratio > DROP_MISSING_RATIO:
        return {"action": "drop_column", "reason": "欠損が多すぎるため列の削除を推奨します。"}
    if ctype == "categorical" and summary.get("unique_ratio", 0) > HIGH_CARDINALITY_RATIO:
        return {"action": "drop_column", "reason": "ID的な列のため説明変数には不適です。"}
    if missing_ratio > 0:
        if ctype == "numeric":
            return {"action": "impute", "method": "median", "reason": "数値列に欠損があります。中央値での補完を推奨します。"}
        return {"action": "impute", "method": "mode", "reason": "カテゴリ列に欠損があります。最頻値での補完を推奨します。"}
    return None


def _f(v) -> float | None:
    try:
        return round(float(v), 4)
    except (TypeError, ValueError):
        return None
