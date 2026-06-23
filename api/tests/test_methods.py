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
