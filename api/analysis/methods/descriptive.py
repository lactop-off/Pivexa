"""記述統計（個別手法編 1）。"""
from __future__ import annotations

import pandas as pd

from .. import charts
from ..base import AnalysisMethod, DatasetProfile
from ..interpret import small_sample_caution
from ..registry import register
from ..schema import (
    AnalysisConfig,
    AnalysisResult,
    ConfigField,
    ConfigSchema,
    InterpretSentence,
    Interpretation,
    Issue,
    Metric,
    ValidationResult,
)


class Descriptive(AnalysisMethod):
    name = "descriptive"
    display_name = "記述統計"
    needs_target = False
    min_rows = 1

    def config_schema(self, dataset: DatasetProfile) -> ConfigSchema:
        return ConfigSchema(
            method=self.name,
            display_name=self.display_name,
            needs_target=False,
            fields=[
                ConfigField(
                    key="explanatory",
                    label="対象列（未選択なら全数値列）",
                    kind="multi_select",
                    required=False,
                    candidates=dataset.numeric,
                )
            ],
        )

    def validate(self, config: AnalysisConfig, dataset: DatasetProfile) -> ValidationResult:
        issues: list[Issue] = []
        if dataset.n_rows < self.min_rows:
            issues.append(Issue(level="error", message="データが空です。"))
        if not dataset.numeric:
            issues.append(Issue(level="error", message="数値列がありません。"))
        return ValidationResult(ok=not any(i.level == "error" for i in issues), issues=issues)

    def run(self, config: AnalysisConfig, df: pd.DataFrame) -> AnalysisResult:
        cols = config.explanatory or [c for c in df.columns if pd.api.types.is_numeric_dtype(df[c])]
        cols = [c for c in cols if pd.api.types.is_numeric_dtype(df[c])]
        desc: dict[str, dict] = {}
        chart_refs = []
        metrics: list[Metric] = []
        for c in cols:
            s = df[c]
            stats = {
                "count": int(s.count()),
                "mean": float(s.mean()),
                "median": float(s.median()),
                "std": float(s.std(ddof=1)) if s.count() > 1 else 0.0,
                "min": float(s.min()),
                "max": float(s.max()),
                "p25": float(s.quantile(0.25)),
                "p50": float(s.quantile(0.50)),
                "p75": float(s.quantile(0.75)),
                "missing": int(s.isna().sum()),
                "skew": float(s.skew()) if s.count() > 2 else 0.0,
            }
            desc[c] = stats
            ref = charts.histogram(s, f"{c} の分布")
            if ref:
                chart_refs.append(ref)
            metrics.append(Metric(key=f"{c}.mean", label=f"{c} 平均", value=round(stats["mean"], 4)))

        return AnalysisResult(
            method=self.name,
            summary_metrics=metrics,
            tables={"describe": desc},
            charts=chart_refs,
            sample_size=len(df),
        )

    def interpret(self, result: AnalysisResult) -> Interpretation:
        sentences: list[InterpretSentence] = []
        for col, stats in result.tables.get("describe", {}).items():
            skew = stats.get("skew", 0.0)
            if skew > 1:
                shape = "右に裾が長い分布です（大きな値が一部にあります）"
            elif skew < -1:
                shape = "左に裾が長い分布です（小さな値が一部にあります）"
            else:
                shape = "概ね左右対称な分布です"
            sentences.append(
                InterpretSentence(
                    level="info",
                    text=f"「{col}」は平均{stats['mean']:.2f}、中央値{stats['median']:.2f}で、{shape}。",
                )
            )
            if stats.get("missing", 0) > 0:
                sentences.append(
                    InterpretSentence(
                        level="caution",
                        text=f"「{col}」には欠損が{stats['missing']}件あります。",
                    )
                )
        c = small_sample_caution(result.sample_size)
        if c:
            sentences.append(c)
        return Interpretation(sentences=sentences)


register(Descriptive())
