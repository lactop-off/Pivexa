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


def bar(labels: list[str], values: list[float], label: str, errors: list[float] | None = None) -> ChartRef | None:
    if not _enabled():
        return None
    fig, ax = _new_fig()
    ax.bar(labels, values, yerr=errors, color="#4C78A8", capsize=4)
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
