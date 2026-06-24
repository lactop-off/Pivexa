"""グラフ生成ユーティリティ（詳細設計書 個別手法編 8）。

matplotlib で PNG を生成し ChartRef を返す。出力先が None の場合は描画を
スキップする（テスト・グラフ不要時のため）。
"""
from __future__ import annotations

import os
import uuid

import pandas as pd

from .schema import ChartRef

# 出力ディレクトリ。None なら描画をスキップ。
_OUTPUT_DIR: str | None = os.environ.get("REPORTS_DIR")


def set_output_dir(path: str | None) -> None:
    global _OUTPUT_DIR
    _OUTPUT_DIR = path


def _enabled() -> bool:
    return _OUTPUT_DIR is not None


def _new_path(prefix: str) -> str:
    assert _OUTPUT_DIR is not None
    os.makedirs(_OUTPUT_DIR, exist_ok=True)
    return os.path.join(_OUTPUT_DIR, f"{prefix}_{uuid.uuid4().hex[:8]}.png")


def _save(fig, path: str) -> None:
    fig.savefig(path, dpi=100, bbox_inches="tight")
    import matplotlib.pyplot as plt

    plt.close(fig)


# 日本語が豆腐(□)にならないよう、利用可能な CJK フォントを優先採用する。
_CJK_FONT_CANDIDATES = (
    "Noto Sans CJK JP", "Noto Sans CJK", "IPAexGothic", "IPAGothic",
    "TakaoPGothic", "VL PGothic", "Yu Gothic", "Hiragino Sans", "MS Gothic",
)
_FONTS_CONFIGURED = False


def _configure_fonts() -> None:
    """初回のみ、CJK 対応フォントを matplotlib に設定する。"""
    global _FONTS_CONFIGURED
    if _FONTS_CONFIGURED:
        return
    import matplotlib
    from matplotlib import font_manager

    available = {f.name for f in font_manager.fontManager.ttflist}
    for name in _CJK_FONT_CANDIDATES:
        if name in available:
            matplotlib.rcParams["font.family"] = name
            break
    # CJK フォントは U+2212(MINUS SIGN) を欠くことがあるため ASCII ハイフンを使う。
    matplotlib.rcParams["axes.unicode_minus"] = False
    _FONTS_CONFIGURED = True


def _new_fig():
    import matplotlib

    matplotlib.use("Agg")
    _configure_fonts()
    import matplotlib.pyplot as plt

    return plt.subplots(figsize=(6, 4))


def histogram(series: pd.Series, label: str) -> ChartRef | None:
    if not _enabled():
        return None
    fig, ax = _new_fig()
    ax.hist(series.dropna(), bins=20, color="#4C78A8")
    ax.set_title(label)
    path = _new_path("hist")
    _save(fig, path)
    return ChartRef(kind="histogram", label=label, path=path)


def heatmap(matrix: pd.DataFrame, label: str) -> ChartRef | None:
    if not _enabled():
        return None
    fig, ax = _new_fig()
    im = ax.imshow(matrix.values, cmap="coolwarm", vmin=-1, vmax=1)
    ax.set_xticks(range(len(matrix.columns)))
    ax.set_xticklabels(matrix.columns, rotation=45, ha="right")
    ax.set_yticks(range(len(matrix.index)))
    ax.set_yticklabels(matrix.index)
    fig.colorbar(im, ax=ax)
    ax.set_title(label)
    path = _new_path("heatmap")
    _save(fig, path)
    return ChartRef(kind="heatmap", label=label, path=path)


def scatter(x: pd.Series, y: pd.Series, label: str, kind: str = "scatter") -> ChartRef | None:
    if not _enabled():
        return None
    fig, ax = _new_fig()
    ax.scatter(x, y, alpha=0.6, color="#4C78A8")
    ax.set_title(label)
    path = _new_path("scatter")
    _save(fig, path)
    return ChartRef(kind=kind, label=label, path=path)


def residual_plot(predicted, residuals, label: str) -> ChartRef | None:
    """残差プロット（個別手法編 6）。

    横軸=予測値、縦軸=残差（実測−予測）の散布図。y=0 に基準線を引き、
    残差が0周りにランダムに散らばっているか（線形性・等分散の前提）を目視確認する。
    """
    if not _enabled():
        return None
    fig, ax = _new_fig()
    ax.scatter(predicted, residuals, alpha=0.6, color="#4C78A8")
    ax.axhline(0, color="gray", linestyle="--")
    ax.set_xlabel("予測値")
    ax.set_ylabel("残差")
    ax.set_title(label)
    path = _new_path("residual")
    _save(fig, path)
    return ChartRef(kind="residual", label=label, path=path)


def bar(labels: list[str], values: list[float], label: str, errors: list[float] | None = None) -> ChartRef | None:
    if not _enabled():
        return None
    fig, ax = _new_fig()
    ax.bar(labels, values, yerr=errors, color="#4C78A8", capsize=4)
    ax.set_title(label)
    path = _new_path("bar")
    _save(fig, path)
    return ChartRef(kind="bar", label=label, path=path)


def confusion_matrix_chart(matrix, labels: list[str], label: str) -> ChartRef | None:
    """混同行列のヒートマップ（個別手法編 8）。

    matrix は [実測][予測] の2x2（行=実測, 列=予測）の件数。各セルに件数を
    注記し、軸に予測（横）/実測（縦）のラベルを付ける。
    """
    if not _enabled():
        return None
    import numpy as np

    mat = np.asarray(matrix, dtype=float)
    fig, ax = _new_fig()
    im = ax.imshow(mat, cmap="Blues")
    ax.set_xticks(range(len(labels)))
    ax.set_xticklabels(labels)
    ax.set_yticks(range(len(labels)))
    ax.set_yticklabels(labels)
    ax.set_xlabel("予測")
    ax.set_ylabel("実測")
    # セルに件数を注記。背景が濃い箇所は白字にして可読性を確保する。
    vmax = mat.max() if mat.size else 0.0
    for i in range(mat.shape[0]):
        for j in range(mat.shape[1]):
            color = "white" if mat[i, j] > vmax / 2 else "black"
            ax.text(j, i, f"{int(round(mat[i, j]))}", ha="center", va="center", color=color)
    fig.colorbar(im, ax=ax)
    ax.set_title(label)
    path = _new_path("confusion")
    _save(fig, path)
    return ChartRef(kind="confusion", label=label, path=path)


def grouped_bar(
    categories: list[str],
    series: dict[str, list[float]],
    label: str,
    legend_title: str | None = None,
) -> ChartRef | None:
    """グループ化棒グラフ（個別手法編 3/8）。

    categories は横軸の主カテゴリ、series は {系列名: 値リスト} で各系列が
    categories と同じ長さの値を持つ。クロス集計表のカテゴリ別件数の可視化に使う。
    """
    if not _enabled():
        return None
    import numpy as np

    fig, ax = _new_fig()
    n_series = len(series) or 1
    x = np.arange(len(categories))
    width = 0.8 / n_series
    for i, (name, values) in enumerate(series.items()):
        offset = (i - (n_series - 1) / 2) * width
        ax.bar(x + offset, values, width=width, label=str(name))
    ax.set_xticks(x)
    ax.set_xticklabels(categories, rotation=45, ha="right")
    if len(series) > 1:
        ax.legend(title=legend_title)
    ax.set_title(label)
    path = _new_path("bar")
    _save(fig, path)
    return ChartRef(kind="bar", label=label, path=path)


def roc_curve_chart(fpr, tpr, label: str) -> ChartRef | None:
    if not _enabled():
        return None
    fig, ax = _new_fig()
    ax.plot(fpr, tpr, color="#4C78A8")
    ax.plot([0, 1], [0, 1], "--", color="gray")
    ax.set_xlabel("False Positive Rate")
    ax.set_ylabel("True Positive Rate")
    ax.set_title(label)
    path = _new_path("roc")
    _save(fig, path)
    return ChartRef(kind="roc", label=label, path=path)
