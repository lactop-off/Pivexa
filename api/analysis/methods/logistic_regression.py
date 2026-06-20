"""ロジスティック回帰（個別手法編 7）。"""
from __future__ import annotations

import numpy as np
import pandas as pd

from .. import charts
from ..base import AnalysisMethod, DatasetProfile
from ..interpret import significance_sentence, small_sample_caution
from ..registry import register
from ..schema import (
    AnalysisConfig,
    AnalysisResult,
    CoefficientRow,
    ConfigField,
    ConfigSchema,
    InterpretSentence,
    Interpretation,
    Issue,
    Metric,
    ValidationResult,
)
from .linear_regression import _dummy_encode


class LogisticRegression(AnalysisMethod):
    name = "logistic_regression"
    display_name = "ロジスティック回帰"
    needs_target = True
    target_kind = "binary"
    min_rows = 10

    def config_schema(self, dataset: DatasetProfile) -> ConfigSchema:
        return ConfigSchema(
            method=self.name,
            display_name=self.display_name,
            needs_target=True,
            target_kind="binary",
            fields=[
                ConfigField(key="target", label="2値の目的変数（Yes/No など）", kind="single_select",
                            required=True, candidates=dataset.numeric + dataset.categorical),
                ConfigField(key="explanatory", label="説明変数（1つ以上）", kind="multi_select",
                            required=True, candidates=dataset.numeric + dataset.categorical),
            ],
        )

    def validate(self, config: AnalysisConfig, dataset: DatasetProfile) -> ValidationResult:
        issues: list[Issue] = []
        if not config.target:
            issues.append(Issue(level="error", message="目的変数を選択してください。"))
        if not config.explanatory:
            issues.append(Issue(level="error", message="説明変数を1つ以上選択してください。"))
        return ValidationResult(ok=not any(i.level == "error" for i in issues), issues=issues)

    def run(self, config: AnalysisConfig, df: pd.DataFrame) -> AnalysisResult:
        import statsmodels.api as sm
        from sklearn.metrics import roc_auc_score, roc_curve

        target = config.target
        cols = config.explanatory
        sub = df[[target] + cols].dropna()

        # 目的変数を0/1へ。positive_label 指定があれば優先。
        raw = sub[target]
        positive = config.options.get("positive_label")
        levels = list(pd.Series(raw.unique()).dropna())
        if len(levels) != 2:
            return AnalysisResult(
                method=self.name, sample_size=len(sub),
                warnings=[f"目的変数が2値ではありません（{len(levels)}水準）。"],
            )
        if positive is None:
            positive = levels[1]
        y = (raw == positive).astype(int)

        X = _dummy_encode(sub, cols).astype(float)
        X = sm.add_constant(X, has_constant="add")

        model = sm.Logit(y, X).fit(disp=False)
        conf = model.conf_int()

        coefs: list[CoefficientRow] = []
        for name in X.columns:
            if name == "const":
                continue
            coefs.append(CoefficientRow(
                variable=name,
                coef=float(model.params[name]),
                std_err=float(model.bse[name]),
                stat=float(model.tvalues[name]),
                p_value=float(model.pvalues[name]),
                ci_low=float(conf.loc[name, 0]),
                ci_high=float(conf.loc[name, 1]),
                extra={"odds_ratio": round(float(np.exp(model.params[name])), 4)},
            ))

        prob = model.predict(X)
        pred = (prob >= 0.5).astype(int)
        accuracy = float((pred == y).mean())
        try:
            auc = float(roc_auc_score(y, prob))
            fpr, tpr, _ = roc_curve(y, prob)
        except ValueError:
            auc, fpr, tpr = float("nan"), [0, 1], [0, 1]

        # 混同行列
        cm = pd.crosstab(y, pred, rownames=["実測"], colnames=["予測"]).to_dict()

        metrics = [
            Metric(key="pseudo_r2", label="疑似R²(McFadden)", value=round(float(model.prsquared), 4)),
            Metric(key="accuracy", label="的中率", value=round(accuracy, 4)),
            Metric(key="auc", label="AUC", value=round(auc, 4) if not np.isnan(auc) else "N/A"),
        ]
        chart_refs = []
        ref = charts.roc_curve_chart(fpr, tpr, "ROC曲線")
        if ref:
            chart_refs.append(ref)

        # クラス不均衡チェック
        warnings = []
        pos_rate = float(y.mean())
        if pos_rate < 0.1 or pos_rate > 0.9:
            warnings.append("クラスの偏りが大きいため、的中率だけでの評価に注意してください。")

        return AnalysisResult(
            method=self.name, summary_metrics=metrics, coefficients=coefs,
            charts=chart_refs, tables={"confusion_matrix": cm, "positive_label": str(positive)},
            sample_size=len(sub), warnings=warnings,
        )

    def interpret(self, result: AnalysisResult) -> Interpretation:
        if not result.summary_metrics:
            return Interpretation(sentences=[InterpretSentence(level="caution", text=" / ".join(result.warnings))])
        sentences: list[InterpretSentence] = []
        m = {x.key: x for x in result.summary_metrics}
        auc = m["auc"].value
        if isinstance(auc, (int, float)):
            if auc >= 0.9:
                q = "優秀"
            elif auc >= 0.8:
                q = "良好"
            elif auc >= 0.7:
                q = "まずまず"
            else:
                q = "低い"
            sentences.append(InterpretSentence(
                level="info", text=f"モデルの判別性能は{q}です（AUC={auc:.2f}）。",
            ))
        for c in result.coefficients:
            if c.p_value is None:
                continue
            sentences.append(significance_sentence(c.variable, c.p_value))
            if c.p_value < 0.05:
                orr = c.extra.get("odds_ratio")
                if orr:
                    sentences.append(InterpretSentence(
                        level="highlight",
                        text=f"「{c.variable}」が1増えると、起こりやすさが約{orr:.2f}倍になります。",
                    ))
        for w in result.warnings:
            sentences.append(InterpretSentence(level="caution", text=w))
        c2 = small_sample_caution(result.sample_size)
        if c2:
            sentences.append(c2)
        return Interpretation(sentences=sentences)


register(LogisticRegression())
