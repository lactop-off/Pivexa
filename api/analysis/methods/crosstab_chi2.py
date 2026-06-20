"""クロス集計＋カイ二乗検定（個別手法編 3）。"""
from __future__ import annotations

import numpy as np
import pandas as pd
from scipy import stats

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


def _cramers_v(chi2: float, n: int, r: int, k: int) -> float:
    denom = n * (min(r, k) - 1)
    return float(np.sqrt(chi2 / denom)) if denom > 0 else 0.0


class CrosstabChi2(AnalysisMethod):
    name = "crosstab_chi2"
    display_name = "クロス集計＋カイ二乗検定"
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
                    label="カテゴリ列（行・列の2列）",
                    kind="multi_select",
                    required=True,
                    candidates=dataset.categorical,
                )
            ],
        )

    def validate(self, config: AnalysisConfig, dataset: DatasetProfile) -> ValidationResult:
        issues: list[Issue] = []
        if len(config.explanatory) != 2:
            issues.append(Issue(level="error", message="カテゴリ列をちょうど2つ選択してください。"))
        return ValidationResult(ok=not any(i.level == "error" for i in issues), issues=issues)

    def run(self, config: AnalysisConfig, df: pd.DataFrame) -> AnalysisResult:
        row_col = config.options.get("row", config.explanatory[0])
        col_col = config.options.get("col", config.explanatory[1])
        sub = df[[row_col, col_col]].dropna()
        observed = pd.crosstab(sub[row_col], sub[col_col])
        chi2, p, dof, expected = stats.chi2_contingency(observed)
        cv = _cramers_v(chi2, observed.values.sum(), observed.shape[0], observed.shape[1])

        warnings = []
        low_cells = (expected < 5).sum()
        total_cells = expected.size
        if total_cells and low_cells / total_cells > 0.2:
            warnings.append("期待度数5未満のセルが多く、カイ二乗検定の前提を満たしていない可能性があります。")

        metrics = [
            Metric(key="chi2", label="カイ二乗値", value=round(float(chi2), 4)),
            Metric(key="p_value", label="P値", value=round(float(p), 4), significant=p < 0.05),
            Metric(key="dof", label="自由度", value=int(dof)),
            Metric(key="cramers_v", label="Cramér's V", value=round(cv, 4)),
        ]
        return AnalysisResult(
            method=self.name,
            summary_metrics=metrics,
            tables={
                "observed": observed.to_dict(),
                "expected": pd.DataFrame(
                    expected, index=observed.index, columns=observed.columns
                ).round(2).to_dict(),
            },
            sample_size=len(sub),
            warnings=warnings,
        )

    def interpret(self, result: AnalysisResult) -> Interpretation:
        m = {x.key: x for x in result.summary_metrics}
        p = float(m["p_value"].value)
        cv = float(m["cramers_v"].value)
        sentences: list[InterpretSentence] = []
        if p < 0.05:
            strength = "強い" if cv >= 0.5 else "中程度の" if cv >= 0.3 else "弱い"
            sentences.append(
                InterpretSentence(
                    level="highlight",
                    text=f"2つの項目には{strength}関連があります（p={p:.3f}, Cramér's V={cv:.2f}）。",
                )
            )
        else:
            sentences.append(
                InterpretSentence(
                    level="info",
                    text=f"2つの項目に統計的な関連は見られません（p={p:.3f}）。",
                )
            )
        for w in result.warnings:
            sentences.append(InterpretSentence(level="caution", text=w))
        c = small_sample_caution(result.sample_size)
        if c:
            sentences.append(c)
        return Interpretation(sentences=sentences)


register(CrosstabChi2())
