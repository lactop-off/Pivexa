"""全手法を import してレジストリに登録する。

新手法を追加したら、ここに import を1行足すだけで有効になる。
"""
from . import (  # noqa: F401
    anova,
    correlation,
    crosstab_chi2,
    descriptive,
    linear_regression,
    logistic_regression,
    ttest,
)
