"""相関分析（個別手法編 2）。"""
from __future__ import annotations

from itertools import combinations

import pandas as pd
from scipy import stats

from .. import charts
from ..base import AnalysisMethod, DatasetProfile
from ..interpret import CAUSALITY_NOTE, small_sample_caution
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


class Correlation(AnalysisMethod):
    name = "correlation"
    display_name = "相関分析"
    needs_target = False
    min_rows = 3

    def config_schema(self, dataset: DatasetProfile) -> ConfigSchema:
        return ConfigSchema(
            method=self.name,
            display_name=self.display_name,
            needs_target=False,
            fields=[
                ConfigField(
                    key="explanatory",
                    label="対象列（2列以上）",
                    kind="multi_select",
                    required=True,
                    candidates=dataset.numeric,
                )
            ],
        )

    def validate(self, config: AnalysisConfig, dataset: DatasetProfile) -> ValidationResult:
        issues: list[Issue] = []
        if len(config.explanatory) < 2:
            issues.append(Issue(level="error", message="数値列を2つ以上選択してください。"))
        if dataset.n_rows < self.min_rows:
            issues.append(Issue(level="error", message="相関の計算には3件以上必要です。"))
        return ValidationResult(ok=not any(i.level == "error" for i in issues), issues=issues)

    def run(self, config: AnalysisConfig, df: pd.DataFrame) -> AnalysisResult:
        method = config.options.get("method", "pearson")
        cols = config.explanatory
        sub = df[cols].dropna()
        corr = sub.corr(method=method)

        pairs = []
        best = None
        for a, b in combinations(cols, 2):
            if method == "spearman":
                r, p = stats.spearmanr(sub[a], sub[b])
            else:
                r, p = stats.pearsonr(sub[a], sub[b])
            row = {"a": a, "b": b, "r": float(r), "p_value": float(p)}
            pairs.append(row)
            if best is None or abs(r) > abs(best["r"]):
                best = row

        chart_refs = []
        h = charts.heatmap(corr, "相関行列")
        if h:
            chart_refs.append(h)
        if best:
            sc = charts.scatter(sub[best["a"]], sub[best["b"]], f"{best['a']} と {best['b']}")
            if sc:
                chart_refs.append(sc)

        metrics: list[Metric] = []
        if best:
            metrics.append(
                Metric(
                    key="strongest_r",
                    label=f"最も強い相関（{best['a']}×{best['b']}）",
                    value=round(best["r"], 4),
                    significant=best["p_value"] < 0.05,
                )
            )

        return AnalysisResult(
            method=self.name,
            summary_metrics=metrics,
            tables={"corr_matrix": corr.round(4).to_dict(), "pairs": pairs},
            charts=chart_refs,
            sample_size=len(sub),
        )

    def interpret(self, result: AnalysisResult) -> Interpretation:
        sentences: list[InterpretSentence] = []
        for pair in result.tables.get("pairs", []):
            r, p = pair["r"], pair["p_value"]
            strength = "強い" if abs(r) >= 0.7 else "中程度の" if abs(r) >= 0.4 else "弱い"
            direction = "正の" if r > 0 else "負の"
            sig = "統計的に有意です" if p < 0.05 else "統計的に有意とは言えません"
            level = "highlight" if (abs(r) >= 0.4 and p < 0.05) else "info"
            sentences.append(
                InterpretSentence(
                    level=level,
                    text=f"「{pair['a']}」と「{pair['b']}」は{strength}{direction}相関（r={r:.2f}）で、{sig}。",
                )
            )
        c = small_sample_caution(result.sample_size)
        if c:
            sentences.append(c)
        sentences.append(CAUSALITY_NOTE)
        return Interpretation(sentences=sentences)


register(Correlation())
