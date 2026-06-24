"""重回帰分析（個別手法編 6）。"""
from __future__ import annotations

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


def _dummy_encode(df: pd.DataFrame, cols: list[str]) -> pd.DataFrame:
    """カテゴリ列をダミー変数化（基準カテゴリ1つを除外）。"""
    cat_cols = [c for c in cols if not pd.api.types.is_numeric_dtype(df[c])]
    if not cat_cols:
        return df[cols].copy()
    return pd.get_dummies(df[cols], columns=cat_cols, drop_first=True)


class LinearRegression(AnalysisMethod):
    name = "linear_regression"
    display_name = "重回帰分析"
    needs_target = True
    target_kind = "numeric"
    min_rows = 10

    def config_schema(self, dataset: DatasetProfile) -> ConfigSchema:
        return ConfigSchema(
            method=self.name,
            display_name=self.display_name,
            needs_target=True,
            target_kind="numeric",
            fields=[
                ConfigField(key="target", label="数値の目的変数", kind="single_select",
                            required=True, candidates=dataset.numeric),
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
        if dataset.n_rows < self.min_rows:
            issues.append(Issue(level="error", message="重回帰には10件以上を推奨します。"))
        # 行数は説明変数の数を上回る必要がある（自由度の確保）。profile で判定可能。
        # 定数項を含めるため n_params = 説明変数の数 + 1 として比較する。
        if config.explanatory and dataset.n_rows <= len(config.explanatory) + 1:
            issues.append(Issue(
                level="error",
                message=f"行数（{dataset.n_rows}）が説明変数の数に対して不足しています。説明変数より十分多い行数が必要です。",
            ))
        if config.target and config.target in config.explanatory:
            issues.append(Issue(level="error", message="目的変数を説明変数に含めないでください。"))
        # 完全多重共線の検出はデータ依存のため run でベストエフォートに行う。
        return ValidationResult(ok=not any(i.level == "error" for i in issues), issues=issues)

    def run(self, config: AnalysisConfig, df: pd.DataFrame) -> AnalysisResult:
        import statsmodels.api as sm
        from statsmodels.stats.outliers_influence import variance_inflation_factor

        target = config.target
        cols = config.explanatory
        sub = df[[target] + cols].dropna()

        # データ依存の前提検査（個別手法編 6）。欠損除去後の行数は profile では
        # 分からないため、行数 <= 説明変数の数+1 のときはここでガードする。
        X_raw = _dummy_encode(sub, cols).astype(float)
        n_params = X_raw.shape[1] + 1  # 定数項を含む
        if len(sub) <= n_params:
            return AnalysisResult(
                method=self.name, sample_size=len(sub),
                warnings=[f"有効データ（{len(sub)}件）が説明変数の数に対して不足しており、重回帰を実行できません。"],
            )

        y = sub[target].astype(float)
        X = sm.add_constant(X_raw, has_constant="add")

        # 完全多重共線（説明変数間の厳密な線形従属）をベストエフォートで検出する。
        # 行列のランクが列数に満たない場合は係数が一意に定まらない。
        import numpy as np

        if np.linalg.matrix_rank(X.values) < X.shape[1]:
            return AnalysisResult(
                method=self.name, sample_size=len(sub),
                warnings=["説明変数の間に完全な相関（多重共線性）があり、係数を一意に推定できません。重複・従属する変数を外してください。"],
            )

        alpha = float(config.options.get("alpha", 0.05))
        standardize = bool(config.options.get("standardize", False))

        model = sm.OLS(y, X).fit()
        conf = model.conf_int()

        # 標準化係数（個別手法編 6）。std_coef = coef * std(x_j) / std(y)。
        # y の標準偏差が0（定数）の場合は計算できないため付与しない。
        std_y = float(y.std(ddof=1))

        # VIF（定数項を除く）
        vifs = {}
        try:
            for i, name in enumerate(X.columns):
                if name == "const":
                    continue
                vifs[name] = float(variance_inflation_factor(X.values, i))
        except Exception:
            vifs = {}

        coefs: list[CoefficientRow] = []
        for name in X.columns:
            if name == "const":
                continue
            extra: dict[str, float] = {}
            if name in vifs:
                extra["vif"] = round(vifs.get(name, float("nan")), 3)
            if standardize and std_y > 0:
                std_x = float(X_raw[name].std(ddof=1))
                extra["std_coef"] = round(float(model.params[name]) * std_x / std_y, 4)
            coefs.append(CoefficientRow(
                variable=name,
                coef=float(model.params[name]),
                std_err=float(model.bse[name]),
                stat=float(model.tvalues[name]),
                p_value=float(model.pvalues[name]),
                ci_low=float(conf.loc[name, 0]),
                ci_high=float(conf.loc[name, 1]),
                extra=extra,
            ))

        metrics = [
            Metric(key="r2", label="R²", value=round(float(model.rsquared), 4)),
            Metric(key="adj_r2", label="調整済みR²", value=round(float(model.rsquared_adj), 4)),
            Metric(key="f", label="F値", value=round(float(model.fvalue), 4)),
            Metric(key="f_pvalue", label="F検定 P値", value=round(float(model.f_pvalue), 4),
                   significant=float(model.f_pvalue) < alpha),
        ]
        chart_refs = []
        pred = model.predict(X)
        ref = charts.scatter(y, pred, "実測値 vs 予測値")
        if ref:
            chart_refs.append(ref)
        # 残差プロット（個別手法編 6）。予測値に対する残差の散らばりを可視化する。
        resid = y - pred
        rref = charts.residual_plot(pred, resid, "残差プロット")
        if rref:
            chart_refs.append(rref)

        warnings = [f"多重共線性に注意（{n} の VIF={v:.1f}）" for n, v in vifs.items() if v >= 10]

        return AnalysisResult(
            method=self.name, summary_metrics=metrics, coefficients=coefs,
            charts=chart_refs,
            tables={"alpha": alpha, "standardized": standardize and std_y > 0},
            sample_size=len(sub), warnings=warnings,
        )

    def interpret(self, result: AnalysisResult) -> Interpretation:
        if not result.summary_metrics:
            return Interpretation(sentences=[
                InterpretSentence(level="caution", text=" / ".join(result.warnings))
            ])
        sentences: list[InterpretSentence] = []
        alpha = float(result.tables.get("alpha", 0.05))
        m = {x.key: x for x in result.summary_metrics}
        r2 = float(m["r2"].value)
        power = "高い" if r2 >= 0.7 else "中程度の" if r2 >= 0.4 else "低い"
        sentences.append(InterpretSentence(
            level="info",
            text=f"モデルの説明力は{power}です（R²={r2:.2f}）。",
        ))
        for c in result.coefficients:
            if c.p_value is None:
                continue
            sentences.append(significance_sentence(c.variable, c.p_value, alpha=alpha))
            if c.p_value < alpha:
                d = "増える" if c.coef > 0 else "減る"
                sentences.append(InterpretSentence(
                    level="highlight",
                    text=f"「{c.variable}」が1増えると目的変数は約{abs(c.coef):.3f}{d}傾向です。",
                ))
        # 標準化係数を出した場合、影響度の比較に使える旨を案内する（個別手法編 6）。
        if result.tables.get("standardized"):
            sentences.append(InterpretSentence(
                level="info",
                text="標準化係数（std_coef）を算出しました。単位の異なる説明変数同士で影響度の大小を比較できます。",
            ))
        for w in result.warnings:
            sentences.append(InterpretSentence(level="caution", text=w))
        c2 = small_sample_caution(result.sample_size)
        if c2:
            sentences.append(c2)
        return Interpretation(sentences=sentences)


register(LinearRegression())
