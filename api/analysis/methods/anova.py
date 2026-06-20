"""分散分析 ANOVA（個別手法編 5）。"""
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


class Anova(AnalysisMethod):
    name = "anova"
    display_name = "分散分析（ANOVA）"
    needs_target = True
    target_kind = "numeric"
    min_rows = 6

    def config_schema(self, dataset: DatasetProfile) -> ConfigSchema:
        return ConfigSchema(
            method=self.name,
            display_name=self.display_name,
            needs_target=True,
            target_kind="numeric",
            fields=[
                ConfigField(key="target", label="数値の対象変数", kind="single_select",
                            required=True, candidates=dataset.numeric),
                ConfigField(key="group", label="3水準以上のグループ列", kind="single_select",
                            required=True, candidates=dataset.categorical),
            ],
        )

    def validate(self, config: AnalysisConfig, dataset: DatasetProfile) -> ValidationResult:
        issues: list[Issue] = []
        if not config.target:
            issues.append(Issue(level="error", message="対象変数を選択してください。"))
        if not config.options.get("group"):
            issues.append(Issue(level="error", message="グループ列を選択してください。"))
        return ValidationResult(ok=not any(i.level == "error" for i in issues), issues=issues)

    def run(self, config: AnalysisConfig, df: pd.DataFrame) -> AnalysisResult:
        import statsmodels.api as sm
        from statsmodels.formula.api import ols
        from statsmodels.stats.multicomp import pairwise_tukeyhsd

        target = config.target
        group = config.options["group"]
        sub = df[[target, group]].dropna().rename(columns={target: "y", group: "g"})
        sub["g"] = sub["g"].astype(str)

        model = ols("y ~ C(g)", data=sub).fit()
        table = sm.stats.anova_lm(model, typ=1)
        f = float(table.loc["C(g)", "F"])
        p = float(table.loc["C(g)", "PR(>F)"])
        ss_between = float(table.loc["C(g)", "sum_sq"])
        ss_within = float(table.loc["Residual", "sum_sq"])

        posthoc_rows = []
        if p < 0.05:
            tukey = pairwise_tukeyhsd(sub["y"], sub["g"])
            for row in tukey.summary().data[1:]:
                posthoc_rows.append({
                    "group1": row[0], "group2": row[1],
                    "meandiff": float(row[2]), "p_adj": float(row[3]),
                    "reject": bool(row[6]),
                })

        means = sub.groupby("g")["y"].agg(["mean", "std"])
        chart_refs = []
        ref = charts.bar(list(means.index), list(means["mean"]),
                         f"{target} の群別平均", errors=list(means["std"].fillna(0)))
        if ref:
            chart_refs.append(ref)

        metrics = [
            Metric(key="F", label="F値", value=round(f, 4)),
            Metric(key="p_value", label="P値", value=round(p, 4), significant=p < 0.05),
            Metric(key="ss_between", label="群間平方和", value=round(ss_between, 4)),
            Metric(key="ss_within", label="群内平方和", value=round(ss_within, 4)),
        ]
        return AnalysisResult(
            method=self.name, summary_metrics=metrics, charts=chart_refs,
            tables={"posthoc": posthoc_rows, "group_means": means.round(4).to_dict()},
            sample_size=len(sub),
        )

    def interpret(self, result: AnalysisResult) -> Interpretation:
        m = {x.key: x for x in result.summary_metrics}
        p = float(m["p_value"].value)
        sentences: list[InterpretSentence] = []
        if p < 0.05:
            sentences.append(InterpretSentence(
                level="highlight",
                text=f"少なくとも1つの群で平均が異なります（F={m['F'].value}, p={p:.3f}）。",
            ))
            for row in result.tables.get("posthoc", []):
                if row["reject"]:
                    sentences.append(InterpretSentence(
                        level="info",
                        text=f"「{row['group1']}」と「{row['group2']}」の間に有意な差があります（p={row['p_adj']:.3f}）。",
                    ))
        else:
            sentences.append(InterpretSentence(
                level="info",
                text=f"群間に統計的な平均差は見られません（p={p:.3f}）。",
            ))
        c = small_sample_caution(result.sample_size)
        if c:
            sentences.append(c)
        return Interpretation(sentences=sentences)


register(Anova())
