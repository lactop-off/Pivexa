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
