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
        # 行数は profile で判定可能。2値判定・各クラス件数はデータ依存のため run でガードする。
        if dataset.n_rows < self.min_rows:
            issues.append(Issue(level="error", message=f"ロジスティック回帰には{self.min_rows}件以上が必要です。"))
        return ValidationResult(ok=not any(i.level == "error" for i in issues), issues=issues)

    def run(self, config: AnalysisConfig, df: pd.DataFrame) -> AnalysisResult:
        import statsmodels.api as sm
        from sklearn.metrics import roc_auc_score, roc_curve

        alpha = float(config.options.get("alpha", 0.05))
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

        # データ依存の前提検査（個別手法編 7）。profile では各クラス件数や
        # 欠損除去後の行数が分からないため、run の冒頭でガードしクラッシュを防ぐ。
        if len(sub) < self.min_rows:
            return AnalysisResult(
                method=self.name, sample_size=len(sub),
                warnings=[f"有効データが{len(sub)}件と少なく、ロジスティック回帰には{self.min_rows}件以上が必要です。"],
            )
        class_counts = raw.value_counts()
        too_small = [str(lv) for lv in levels if int(class_counts.get(lv, 0)) < 5]
        if too_small:
            return AnalysisResult(
                method=self.name, sample_size=len(sub),
                warnings=[f"各クラスに5件以上必要ですが、件数が不足するクラスがあります（{', '.join(too_small)}）。"],
            )
        if positive is None:
            # 既定は「大きい方の値」を陽性とする。0/1 なら 1、Yes/No なら "Yes"。
            # これによりオッズ比の向きが直感に沿う（出現順依存を解消）。
            positive = sorted(levels)[-1]
        y = (raw == positive).astype(int)

        X = _dummy_encode(sub, cols).astype(float)
        X = sm.add_constant(X, has_constant="add")

        # 完全分離・特異行列では (a) 例外送出 (b) 収束失敗(発散パラメータ) の
        # どちらも起こりうる。両方を graceful に警告へ変換し、ジョブを error にしない。
        try:
            model = sm.Logit(y, X).fit(disp=False)
        except Exception:  # noqa: BLE001  特異行列など数値的に推定不能
            model = None
        if model is None or not getattr(model, "mle_retvals", {}).get("converged", True):
            return AnalysisResult(
                method=self.name, sample_size=len(sub),
                warnings=[
                    "データが完全に分離しているなどの理由でモデルを推定できませんでした"
                    "（説明変数が目的変数をほぼ完全に説明している可能性があります）。"
                ],
            )
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

        # 混同行列（行=実測, 列=予測）。予測が片側に偏っても 0/1 の2x2を保つよう
        # reindex で欠けた行・列を 0 埋めする。
        cm_df = (
            pd.crosstab(y, pred, rownames=["実測"], colnames=["予測"])
            .reindex(index=[0, 1], columns=[0, 1], fill_value=0)
        )
        cm = cm_df.to_dict()
        # 表示は陽性ラベルに合わせ「0=陰性 / 1=陽性」を明示する。
        cm_labels = [f"0（非{positive}）", f"1（{positive}）"]

        metrics = [
            Metric(key="pseudo_r2", label="疑似R²(McFadden)", value=round(float(model.prsquared), 4)),
            Metric(key="accuracy", label="的中率", value=round(accuracy, 4)),
            Metric(key="auc", label="AUC", value=round(auc, 4) if not np.isnan(auc) else "N/A"),
        ]
        chart_refs = []
        ref = charts.roc_curve_chart(fpr, tpr, "ROC曲線")
        if ref:
            chart_refs.append(ref)
        # 混同行列の図（個別手法編 8）。
        cref = charts.confusion_matrix_chart(cm_df.values, cm_labels, "混同行列")
        if cref:
            chart_refs.append(cref)

        # クラス不均衡チェック
        warnings = []
        pos_rate = float(y.mean())
        if pos_rate < 0.1 or pos_rate > 0.9:
            warnings.append("クラスの偏りが大きいため、的中率だけでの評価に注意してください。")

        return AnalysisResult(
            method=self.name, summary_metrics=metrics, coefficients=coefs,
            charts=chart_refs,
            tables={"confusion_matrix": cm, "positive_label": str(positive), "alpha": alpha},
            sample_size=len(sub), warnings=warnings,
        )

    def interpret(self, result: AnalysisResult) -> Interpretation:
        if not result.summary_metrics:
            return Interpretation(sentences=[InterpretSentence(level="caution", text=" / ".join(result.warnings))])
        sentences: list[InterpretSentence] = []
        alpha = float(result.tables.get("alpha", 0.05))
        positive = result.tables.get("positive_label")
        if positive is not None:
            sentences.append(InterpretSentence(
                level="info",
                text=f"「{positive}」を陽性（=起こった側）として分析しています。オッズ比はこの向きでの値です。",
            ))
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
            sentences.append(significance_sentence(c.variable, c.p_value, alpha=alpha))
            if c.p_value < alpha:
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
