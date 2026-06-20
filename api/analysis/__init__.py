"""分析フレーム。

import 時に全手法を登録する。
"""
from . import methods  # noqa: F401  （レジストリ登録の副作用を起こす）
from .base import AnalysisMethod, DatasetProfile
from .registry import get_method, list_methods, register
from .schema import (
    AnalysisConfig,
    AnalysisResult,
    ConfigSchema,
    Interpretation,
    ValidationResult,
)

__all__ = [
    "AnalysisMethod",
    "DatasetProfile",
    "get_method",
    "list_methods",
    "register",
    "AnalysisConfig",
    "AnalysisResult",
    "ConfigSchema",
    "Interpretation",
    "ValidationResult",
]
