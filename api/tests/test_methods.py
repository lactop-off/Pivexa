"""分析フレーム＋7手法のスモークテスト。

合成データで各手法が validate→run→interpret を通り、共通スキーマの結果を
返すことを確認する。グラフ出力は無効（REPORTS_DIR 未設定）。
"""
from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from analysis import get_method, list_methods
from analysis.base import DatasetProfile
from analysis.runner import run_analysis
from analysis.schema import AnalysisConfig


@pytest.fixture
def df() -> pd.DataFrame:
    rng = np.random.default_rng(42)
    n = 120
    ad = rng.normal(100, 20, n)
    temp = rng.normal(25, 5, n)
    group = rng.choice(["A", "B", "C"], n)
    region = rng.choice(["東", "西"], n)
    noise = rng.normal(0, 5, n)
    sales = 2 * ad + 1.5 * temp + noise
    buy = (sales > sales.mean()).astype(int)
    return pd.DataFrame({
        "ad_cost": ad, "temp": temp, "group": group,
        "region": region, "sales": sales, "buy": buy,
    })


def test_all_seven_methods_registered():
    names = {m.name for m in list_methods()}
    assert names == {
        "descriptive", "correlation", "crosstab_chi2",
        "ttest", "anova", "linear_regression", "logistic_regression",
    }


def test_descriptive(df):
    cfg = AnalysisConfig(method="descriptive", explanatory=["ad_cost", "sales"])
    res, interp = run_analysis(cfg, df)
    assert res.sample_size == len(df)
    assert "describe" in res.tables
    assert interp.sentences


def test_correlation(df):
    cfg = AnalysisConfig(method="correlation", explanatory=["ad_cost", "temp", "sales"])
    res, interp = run_analysis(cfg, df)
    assert res.tables["pairs"]
    assert any(s.level == "caution" for s in interp.sentences)  # 因果注意


def test_crosstab(df):
    cfg = AnalysisConfig(method="crosstab_chi2", explanatory=["group", "region"])
    res, interp = run_analysis(cfg, df)
    keys = {m.key for m in res.summary_metrics}
    assert {"chi2", "p_value", "cramers_v"} <= keys


def test_ttest(df):
    cfg = AnalysisConfig(method="ttest", target="sales", options={"group": "region"})
    res, interp = run_analysis(cfg, df)
    assert any(m.key == "cohens_d" for m in res.summary_metrics)


def test_anova(df):
    cfg = AnalysisConfig(method="anova", target="sales", options={"group": "group"})
    res, interp = run_analysis(cfg, df)
    assert any(m.key == "F" for m in res.summary_metrics)


def test_linear_regression(df):
    cfg = AnalysisConfig(method="linear_regression", target="sales",
                         explanatory=["ad_cost", "temp", "region"])
    res, interp = run_analysis(cfg, df)
    vars_ = {c.variable for c in res.coefficients}
    assert "ad_cost" in vars_
    # ad_cost は強く効いているはず
    ad = next(c for c in res.coefficients if c.variable == "ad_cost")
    assert ad.p_value < 0.05
    r2 = next(m for m in res.summary_metrics if m.key == "r2")
    assert float(r2.value) > 0.8


def test_logistic_regression(df):
    cfg = AnalysisConfig(method="logistic_regression", target="buy",
                         explanatory=["ad_cost", "temp"])
    res, interp = run_analysis(cfg, df)
    assert any(m.key == "auc" for m in res.summary_metrics)
    assert all("odds_ratio" in c.extra for c in res.coefficients)
    # 既定で大きい方の値(1)を陽性とするため、buy と正の関係にある ad_cost の
    # オッズ比は1より大きい（向きが直感に沿う）。
    assert res.tables["positive_label"] == "1"
    ad = next(c for c in res.coefficients if c.variable == "ad_cost")
    assert ad.extra["odds_ratio"] > 1


def test_validate_catches_bad_config(df):
    method = get_method("correlation")
    profile = DatasetProfile.from_dataframe(df)
    vr = method.validate(AnalysisConfig(method="correlation", explanatory=["ad_cost"]), profile)
    assert vr.has_error


def test_logistic_emits_confusion_chart(df, tmp_path):
    """logistic 実行時、charts に混同行列(kind=confusion)が含まれること。"""
    from analysis import charts

    charts.set_output_dir(str(tmp_path))
    try:
        cfg = AnalysisConfig(method="logistic_regression", target="buy",
                             explanatory=["ad_cost", "temp"])
        res, _ = run_analysis(cfg, df)
    finally:
        charts.set_output_dir(None)
    kinds = {c.kind for c in res.charts}
    assert "confusion" in kinds
    # ROC も併せて出力される。
    assert "roc" in kinds


def test_crosstab_emits_bar_chart(df, tmp_path):
    """crosstab 実行時、charts に棒グラフ(kind=bar)が含まれること。"""
    from analysis import charts

    charts.set_output_dir(str(tmp_path))
    try:
        cfg = AnalysisConfig(method="crosstab_chi2", explanatory=["group", "region"])
        res, _ = run_analysis(cfg, df)
    finally:
        charts.set_output_dir(None)
    assert any(c.kind == "bar" for c in res.charts)


def test_anova_validate_rejects_non_numeric_target(df):
    """anova の validate は数値でない対象変数をエラーにする（profileで判定可能）。"""
    method = get_method("anova")
    profile = DatasetProfile.from_dataframe(df)
    vr = method.validate(
        AnalysisConfig(method="anova", target="group", options={"group": "region"}),
        profile,
    )
    assert vr.has_error


def test_anova_run_guards_two_level_group():
    """anova の run は群が2水準しかない場合、クラッシュせずエラーで返す。"""
    small = pd.DataFrame({
        "y": [1.0, 2, 3, 4, 5, 6],
        "g": ["A", "A", "A", "B", "B", "B"],  # 2水準のみ
    })
    cfg = AnalysisConfig(method="anova", target="y", options={"group": "g"})
    res, interp = run_analysis(cfg, small)
    # 正常系の指標は出ず、警告にエラーメッセージが入る。interpret も落ちない。
    assert not res.summary_metrics
    assert res.warnings
    assert interp.sentences


def test_logistic_run_guards_tiny_class():
    """logistic の run は各クラス<5件のとき、クラッシュせずエラーで返す。"""
    small = pd.DataFrame({
        "x": list(range(12)),
        "y": [0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 1, 1],  # 陽性が2件のみ(<5)
    })
    cfg = AnalysisConfig(method="logistic_regression", target="y", explanatory=["x"])
    res, interp = run_analysis(cfg, small)
    assert not res.summary_metrics
    assert res.warnings
    assert interp.sentences


def test_ttest_run_guards_single_observation_group():
    """ttest の run は片群が1件以下のとき、クラッシュせずエラーで返す。"""
    small = pd.DataFrame({
        "y": [1.0, 2.0, 3.0, 4.0],
        "g": ["A", "A", "A", "B"],  # B が1件のみ
    })
    cfg = AnalysisConfig(method="ttest", target="y", options={"group": "g"})
    res, interp = run_analysis(cfg, small)
    assert not res.summary_metrics
    assert res.warnings
    assert interp.sentences


def test_crosstab_run_guards_single_category():
    """crosstab の run は片方の列が1カテゴリしかないとき、エラーで返す。"""
    small = pd.DataFrame({
        "a": ["X", "X", "X", "X"],  # 1カテゴリのみ
        "b": ["P", "Q", "P", "Q"],
    })
    cfg = AnalysisConfig(method="crosstab_chi2", explanatory=["a", "b"])
    res, interp = run_analysis(cfg, small)
    assert not res.summary_metrics
    assert res.warnings
    assert interp.sentences


def test_linear_validate_rejects_too_few_rows_for_vars(df):
    """linear の validate は行数が説明変数の数以下のときエラー（profileで判定可能）。"""
    method = get_method("linear_regression")
    # 行数3、説明変数3 -> n_rows <= len+1
    tiny_profile = DatasetProfile(
        {"sales": "numeric", "ad_cost": "numeric", "temp": "numeric", "region": "categorical"},
        n_rows=3,
    )
    vr = method.validate(
        AnalysisConfig(method="linear_regression", target="sales",
                       explanatory=["ad_cost", "temp", "region"]),
        tiny_profile,
    )
    assert vr.has_error


def test_linear_run_guards_perfect_collinearity():
    """linear の run は完全多重共線のとき、クラッシュせずエラーで返す。"""
    n = 20
    x1 = np.arange(n, dtype=float)
    small = pd.DataFrame({
        "y": x1 + 1.0,
        "x1": x1,
        "x2": x1 * 2.0,  # x1 と完全従属
    })
    cfg = AnalysisConfig(method="linear_regression", target="y",
                         explanatory=["x1", "x2"])
    res, interp = run_analysis(cfg, small)
    assert not res.summary_metrics
    assert res.warnings
    assert interp.sentences


def test_logistic_run_guards_perfect_separation():
    """logistic は完全分離データでも 500/例外でなく、警告付きで graceful に返す。"""
    # x が小さいと必ず y=0、大きいと必ず y=1（完全分離）。各クラス6件で件数ガードは通過。
    small = pd.DataFrame({
        "x": [0.0, 1, 2, 3, 4, 5, 100, 101, 102, 103, 104, 105],
        "y": [0, 0, 0, 0, 0, 0, 1, 1, 1, 1, 1, 1],
    })
    cfg = AnalysisConfig(method="logistic_regression", target="y", explanatory=["x"])
    res, interp = run_analysis(cfg, small)
    assert not res.summary_metrics
    assert res.warnings
    assert interp.sentences


def test_linear_emits_residual_chart(df, tmp_path):
    """linear 実行時、charts に残差プロット(kind=residual)が含まれること（個別手法編 6）。"""
    from analysis import charts

    charts.set_output_dir(str(tmp_path))
    try:
        cfg = AnalysisConfig(method="linear_regression", target="sales",
                             explanatory=["ad_cost", "temp", "region"])
        res, _ = run_analysis(cfg, df)
    finally:
        charts.set_output_dir(None)
    kinds = {c.kind for c in res.charts}
    assert "residual" in kinds
    # 既存の予測vs実測 scatter も併せて出力される（非回帰）。
    assert "scatter" in kinds


def test_linear_standardized_coefficients(df):
    """options.standardize=True で係数の extra に std_coef が入る（個別手法編 6）。"""
    cfg = AnalysisConfig(method="linear_regression", target="sales",
                         explanatory=["ad_cost", "temp"],
                         options={"standardize": True})
    res, interp = run_analysis(cfg, df)
    assert all("std_coef" in c.extra for c in res.coefficients)
    # 標準化係数を出した旨の解釈文が1つ追加される。
    assert any("標準化係数" in s.text for s in interp.sentences)


def test_linear_no_standardized_by_default(df):
    """standardize 未指定（既定）では std_coef を付与しない（非回帰）。"""
    cfg = AnalysisConfig(method="linear_regression", target="sales",
                         explanatory=["ad_cost", "temp"])
    res, _ = run_analysis(cfg, df)
    assert all("std_coef" not in c.extra for c in res.coefficients)


def test_significance_sentence_alpha_changes_verdict():
    """significance_sentence は alpha により有意/非有意の文言が変わる（個別手法編 0）。"""
    from analysis.interpret import significance_sentence

    # p=0.07 は alpha=0.05 では非有意、alpha=0.10 では有意。
    s05 = significance_sentence("x", 0.07, alpha=0.05)
    s10 = significance_sentence("x", 0.07, alpha=0.10)
    assert s05.level == "info"
    assert "有意とは言えません" in s05.text
    assert s10.level == "highlight"
    assert "有意です" in s10.text
    # 既定（alpha=0.05）は従来挙動（非回帰）。
    assert significance_sentence("x", 0.07).level == "info"


def test_alpha_affects_significance_flag(df):
    """alpha=0.1 と既定0.05 で Metric.significant の判定が変わりうる構成を確認。"""
    # p値が 0.05〜0.10 程度になる弱い相関ペアを合成する（seed/係数を固定）。
    rng = np.random.default_rng(60)
    n = 60
    x = rng.normal(0, 1, n)
    # わずかに相関させ、p を 0.05 近傍（≈0.064）に乗せる。
    y = 0.27 * x + rng.normal(0, 1, n)
    small = pd.DataFrame({"x": x, "y": y})
    cfg = AnalysisConfig(method="correlation", explanatory=["x", "y"])
    res05, _ = run_analysis(cfg, small)
    p = res05.tables["pairs"][0]["p_value"]
    if not (0.05 <= p < 0.10):
        pytest.skip(f"合成データの p={p:.3f} が 0.05〜0.10 の範囲外（環境差）")
    cfg10 = AnalysisConfig(method="correlation", explanatory=["x", "y"],
                           options={"alpha": 0.10})
    res10, _ = run_analysis(cfg10, small)
    m05 = next(m for m in res05.summary_metrics if m.key == "strongest_r")
    m10 = next(m for m in res10.summary_metrics if m.key == "strongest_r")
    assert m05.significant is False
    assert m10.significant is True


def test_anova_posthoc_disabled(df):
    """options.posthoc=False で posthoc テーブルが空になる（個別手法編 5）。"""
    cfg = AnalysisConfig(method="anova", target="sales",
                         options={"group": "group", "posthoc": False})
    res, _ = run_analysis(cfg, df)
    assert res.tables["posthoc"] == []


def test_anova_posthoc_enabled_by_default(df):
    """posthoc 既定（True）では全体が有意なとき posthoc が生成される（非回帰）。"""
    cfg = AnalysisConfig(method="anova", target="sales", options={"group": "group"})
    res, _ = run_analysis(cfg, df)
    p = next(m for m in res.summary_metrics if m.key == "p_value")
    if p.significant:
        assert res.tables["posthoc"]


def test_charts_render_japanese_without_missing_glyph(tmp_path):
    """日本語ラベルのグラフでフォント欠落(豆腐)が起きないこと。"""
    import warnings

    from matplotlib import font_manager

    from analysis import charts

    available = {f.name for f in font_manager.fontManager.ttflist}
    if not any(n in available for n in charts._CJK_FONT_CANDIDATES):
        pytest.skip("CJK フォント未導入のためスキップ")

    charts.set_output_dir(str(tmp_path))
    try:
        with warnings.catch_warnings(record=True) as caught:
            warnings.simplefilter("always")
            ref = charts.histogram(pd.Series([1.0, 2, 3, 4, 5]), "売上の分布")
    finally:
        charts.set_output_dir(None)

    assert ref is not None
    missing = [w for w in caught if "missing from font" in str(w.message)]
    assert not missing, f"日本語グリフが欠落しています: {[str(w.message) for w in missing]}"
