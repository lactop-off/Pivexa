"""共通スキーマ（詳細設計書 共通基盤編 3.3）。

全分析手法の設定・結果・解釈をこのスキーマで表現する。フロント・API・worker は
個別手法を知らず、このスキーマのみに依存して描画・保存・受け渡しを行う。
"""
from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field


# --- 設定スキーマ -----------------------------------------------------------
class ConfigField(BaseModel):
    key: str  # "target" | "explanatory" | "group" など
    label: str
    kind: str  # "single_select" | "multi_select" | "option"
    required: bool
    candidates: list[str] = Field(default_factory=list)  # 選択可能な列名


class ConfigSchema(BaseModel):
    method: str
    display_name: str
    needs_target: bool
    target_kind: str | None = None
    fields: list[ConfigField] = Field(default_factory=list)


class AnalysisConfig(BaseModel):
    method: str
    target: str | None = None
    explanatory: list[str] = Field(default_factory=list)
    options: dict[str, Any] = Field(default_factory=dict)


# --- 検証 -------------------------------------------------------------------
class Issue(BaseModel):
    level: str  # "error" | "warning"
    message: str


class ValidationResult(BaseModel):
    ok: bool
    issues: list[Issue] = Field(default_factory=list)

    @property
    def has_error(self) -> bool:
        return any(i.level == "error" for i in self.issues)


# --- 結果 -------------------------------------------------------------------
class Metric(BaseModel):
    key: str
    label: str
    value: float | int | str
    significant: bool | None = None


class CoefficientRow(BaseModel):
    variable: str
    coef: float
    std_err: float | None = None
    stat: float | None = None  # t値/z値
    p_value: float | None = None
    ci_low: float | None = None
    ci_high: float | None = None
    extra: dict[str, float] = Field(default_factory=dict)  # オッズ比/VIF など


class ChartRef(BaseModel):
    kind: str  # "histogram" | "scatter" | "heatmap" | "bar" | "roc" | "confusion"
    label: str
    path: str


class AnalysisResult(BaseModel):
    method: str
    summary_metrics: list[Metric] = Field(default_factory=list)
    coefficients: list[CoefficientRow] = Field(default_factory=list)
    tables: dict[str, Any] = Field(default_factory=dict)
    charts: list[ChartRef] = Field(default_factory=list)
    sample_size: int = 0
    warnings: list[str] = Field(default_factory=list)


# --- 解釈 -------------------------------------------------------------------
class InterpretSentence(BaseModel):
    level: str  # "info" | "highlight" | "caution"
    text: str


class Interpretation(BaseModel):
    sentences: list[InterpretSentence] = Field(default_factory=list)
