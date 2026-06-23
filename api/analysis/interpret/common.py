"""テンプレート解釈エンジンの共通部品（詳細設計書 共通基盤編 4.2）。

外部 LLM に依存せず、指標値の閾値判定で定型文を選び変数名・数値を差し込む。
"""
from __future__ import annotations

from ..schema import InterpretSentence

P_SIGNIFICANT = 0.05


def significance_sentence(var: str, p: float, alpha: float = 0.05) -> InterpretSentence:
    """有意性の定型文を返す（個別手法編 0 共通事項）。

    判定の境界には呼び出し側の有意水準 alpha を用いる（既定 0.05 で後方互換）。
    「強く有意」の閾値は alpha の 1/5（既定 0.01）として alpha に追従させる。
    """
    if p < alpha / 5:
        return InterpretSentence(
            level="highlight",
            text=f"「{var}」は統計的に強く有意です（p={p:.3f}）。偶然とは考えにくい関係があります。",
        )
    if p < alpha:
        return InterpretSentence(
            level="highlight",
            text=f"「{var}」は統計的に有意です（p={p:.3f}）。",
        )
    return InterpretSentence(
        level="info",
        text=f"「{var}」は統計的に有意とは言えません（p={p:.3f}）。",
    )


def small_sample_caution(n: int, threshold: int = 30) -> InterpretSentence | None:
    if n < threshold:
        return InterpretSentence(
            level="caution",
            text=f"サンプル数が{n}件と少なめです。結果は参考程度にとどめてください。",
        )
    return None


CAUSALITY_NOTE = InterpretSentence(
    level="caution",
    text="統計的な関係は必ずしも因果関係を意味しません。結果の解釈にはご注意ください。",
)
