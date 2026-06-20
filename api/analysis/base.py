"""分析手法の抽象基底（詳細設計書 共通基盤編 3.1）。

各手法はこの契約を実装する。共通基盤（フロント・API・worker）はこの契約のみに
依存し、個別手法の中身を知らない。新手法の追加は methods/ にファイルを足し、
レジストリに登録するだけで完結する。
"""
from __future__ import annotations

from abc import ABC, abstractmethod

import pandas as pd

from .schema import (
    AnalysisConfig,
    AnalysisResult,
    ConfigSchema,
    Interpretation,
    ValidationResult,
)


class DatasetProfile:
    """設定スキーマ生成・検証に必要な最小限のデータ情報。

    実運用では dataset_columns（プロファイリング結果）から構築する。
    """

    def __init__(self, columns: dict[str, str], n_rows: int):
        # columns: {列名: 推定型("numeric"|"datetime"|"categorical")}
        self.columns = columns
        self.n_rows = n_rows

    def by_type(self, *kinds: str) -> list[str]:
        return [c for c, t in self.columns.items() if t in kinds]

    @property
    def numeric(self) -> list[str]:
        return self.by_type("numeric")

    @property
    def categorical(self) -> list[str]:
        return self.by_type("categorical")

    @classmethod
    def from_dataframe(cls, df: pd.DataFrame) -> "DatasetProfile":
        cols: dict[str, str] = {}
        for c in df.columns:
            if pd.api.types.is_numeric_dtype(df[c]):
                cols[c] = "numeric"
            elif pd.api.types.is_datetime64_any_dtype(df[c]):
                cols[c] = "datetime"
            else:
                cols[c] = "categorical"
        return cls(cols, len(df))


class AnalysisMethod(ABC):
    name: str
    display_name: str
    needs_target: bool = False
    target_kind: str | None = None  # "numeric" | "binary" | "categorical" | None
    min_rows: int = 1

    @abstractmethod
    def config_schema(self, dataset: DatasetProfile) -> ConfigSchema:
        """設定画面に必要な入力定義を返す（選択可能な変数候補を含む）。"""

    @abstractmethod
    def validate(
        self, config: AnalysisConfig, dataset: DatasetProfile
    ) -> ValidationResult:
        """設定とデータの整合性を検証。"""

    @abstractmethod
    def run(self, config: AnalysisConfig, df: pd.DataFrame) -> AnalysisResult:
        """解析を実行し共通形式の結果を返す。"""

    @abstractmethod
    def interpret(self, result: AnalysisResult) -> Interpretation:
        """結果からテンプレート解釈文を生成する。"""
