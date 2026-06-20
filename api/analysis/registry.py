"""手法レジストリ（詳細設計書 共通基盤編 3.2）。"""
from __future__ import annotations

from .base import AnalysisMethod

_REGISTRY: dict[str, AnalysisMethod] = {}


class UnknownMethodError(KeyError):
    pass


def register(method: AnalysisMethod) -> None:
    _REGISTRY[method.name] = method


def get_method(name: str) -> AnalysisMethod:
    if name not in _REGISTRY:
        raise UnknownMethodError(name)
    return _REGISTRY[name]


def list_methods() -> list[AnalysisMethod]:
    return list(_REGISTRY.values())
