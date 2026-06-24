"""t検定（個別手法編 4）。"""
from __future__ import annotations

import numpy as np
import pandas as pd
from scipy import stats

from .. import charts
from ..base import AnalysisMethod, DatasetProfile
from ..interpret import significance_sentence, small_sample_caution
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


def _cohens_d(a: pd.Series, b: pd.Series) -> float:
    na, nb = len(a), len(b)
    pooled = np.sqrt(((na - 1) * a.std(ddof=1) ** 2 + (nb - 1) * b.std(ddof=1) ** 2) / (na + nb - 2))
    return float((a.mean() - b.mean()) / pooled) if pooled > 0 else 0.0


class TTest(AnalysisMethod):
    name = "ttest"
    display_name = "t検定"
    needs_target = True
    target_kind = "numeric"
    min_rows = 4

    def config_schema(self, dataset: DatasetProfile) -> ConfigSchema:
        return ConfigSchema(
            method=self.name,
            display_name=self.display_name,
            needs_target=True,
            target_kind="numeric",
            fields=[
                ConfigField(key="target", label="数値の対象変数", kind="single_select",
                            required=True, candidates=dataset.numeric),
                ConfigField(key="group", label="2群のグループ列", kind="single_select",
                            required=True, candidates=dataset.categorical),
            ],
        )

    def validate(self, config: AnalysisConfig, dataset: DatasetProfile) -> ValidationResult:
        issues: list[Issue] = []
        if not config.target:
            issues.append(Issue(level="error", message="対象変数を選択してください。"))
        elif dataset.columns.get(config.target) not in (None, "numeric"):
            # 対象変数の型は profile で判定可能。数値以外はエラー。
            issues.append(Issue(level="error", message="対象変数には数値の列を選択してください。"))
        group = config.options.get("group")
        if not group:
            issues.append(Issue(level="error", message="グループ列を選択してください。"))
        elif group == config.target:
            issues.append(Issue(level="error", message="対象変数とグループ列には別の列を選んでください。"))
        # 群がちょうど2水準か・各群 n>=2 はデータ依存のため run でガードする。
        return ValidationResult(ok=not any(i.level == "error" for i in issues), issues=issues)

    def run(self, config: AnalysisConfig, df: pd.DataFrame) -> AnalysisResult:
        target = config.target
        group = config.options["group"]
        equal_var = bool(config.options.get("equal_var", False))
        paired = bool(config.options.get("paired", False))

        sub = df[[target, group]].dropna()
        levels = list(sub[group].unique())
        if len(levels) != 2:
            return AnalysisResult(
                method=self.name, sample_size=len(sub),
                warnings=[f"グループ列の水準数が2ではありません（{len(levels)}水準）。"],
            )
        a = sub[sub[group] == levels[0]][target]
        b = sub[sub[group] == levels[1]][target]

        # 各群 n>=2 はデータ依存（profile では群サイズ不明）のため run でガードする。
        if len(a) < 2 or len(b) < 2:
            return AnalysisResult(
                method=self.name, sample_size=len(sub),
                warnings=[f"各群に2件以上必要です（{levels[0]}={len(a)}件, {levels[1]}={len(b)}件）。"],
            )

        if paired:
            n = min(len(a), len(b))
            t, p = stats.ttest_rel(a.iloc[:n], b.iloc[:n])
        else:
            t, p = stats.ttest_ind(a, b, equal_var=equal_var)

        mean_diff = float(a.mean() - b.mean())
        # 平均差の95%CI（Welch近似）
        se = np.sqrt(a.var(ddof=1) / len(a) + b.var(ddof=1) / len(b))
        ci_low, ci_high = mean_diff - 1.96 * se, mean_diff + 1.96 * se
        d = _cohens_d(a, b)

        metrics = [
            Metric(key="mean_a", label=f"{levels[0]} の平均", value=round(float(a.mean()), 4)),
            Metric(key="mean_b", label=f"{levels[1]} の平均", value=round(float(b.mean()), 4)),
            Metric(key="mean_diff", label="平均差", value=round(mean_diff, 4)),
            Metric(key="t", label="t値", value=round(float(t), 4)),
            Metric(key="p_value", label="P値", value=round(float(p), 4), significant=p < 0.05),
            Metric(key="ci_low", label="差の95%CI下限", value=round(float(ci_low), 4)),
            Metric(key="ci_high", label="差の95%CI上限", value=round(float(ci_high), 4)),
            Metric(key="cohens_d", label="効果量 (Cohen's d)", value=round(d, 4)),
        ]
        chart_refs = []
        ref = charts.bar([str(levels[0]), str(levels[1])], [float(a.mean()), float(b.mean())],
                         f"{target} の群別平均", errors=[float(a.std(ddof=1)), float(b.std(ddof=1))])
        if ref:
            chart_refs.append(ref)

        return AnalysisResult(
            method=self.name, summary_metrics=metrics, charts=chart_refs,
            tables={"levels": [str(x) for x in levels]}, sample_size=len(sub),
        )

    def interpret(self, result: AnalysisResult) -> Interpretation:
        if not result.summary_metrics:
            return Interpretation(sentences=[InterpretSentence(level="caution", text=" / ".join(result.warnings))])
        m = {x.key: x for x in result.summary_metrics}
        p = float(m["p_value"].value)
        diff = float(m["mean_diff"].value)
        d = abs(float(m["cohens_d"].value))
        sentences = [significance_sentence("2群の平均差", p)]
        if p < 0.05:
            rel = "高い" if diff > 0 else "低い"
            size = "大きな" if d >= 0.8 else "中程度の" if d >= 0.5 else "小さな"
            sentences.append(InterpretSentence(
                level="highlight",
                text=f"片方の群の平均がもう片方より{rel}結果です（効果量は{size}差）。",
            ))
        c = small_sample_caution(result.sample_size)
        if c:
            sentences.append(c)
        return Interpretation(sentences=sentences)


register(TTest())
