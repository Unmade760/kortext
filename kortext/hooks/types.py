"""
Core data types and results for kortext hooks and pipelines.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from types import MappingProxyType
from typing import Any, Mapping, Optional


@dataclass(frozen=True)
class InterceptorResult:
    """Immutable result from an individual interceptor check."""

    decision: str = "allow"  # "allow", "deny", "continue", "stop", "ask"
    reason: Optional[str] = None
    data: Optional[Mapping[str, Any]] = None

    @classmethod
    def allow(
        cls,
        reason: Optional[str] = None,
        data: Optional[Mapping[str, Any]] = None,
    ) -> "InterceptorResult":
        return cls(decision="allow", reason=reason, data=data)

    @classmethod
    def deny(
        cls,
        reason: str,
        data: Optional[Mapping[str, Any]] = None,
    ) -> "InterceptorResult":
        return cls(decision="deny", reason=reason, data=data)

    @classmethod
    def stop(
        cls,
        reason: Optional[str] = None,
        data: Optional[Mapping[str, Any]] = None,
    ) -> "InterceptorResult":
        return cls(decision="stop", reason=reason, data=data)

    @classmethod
    def continue_execution(
        cls,
        reason: str,
        data: Optional[Mapping[str, Any]] = None,
    ) -> "InterceptorResult":
        return cls(decision="continue", reason=reason, data=data)


@dataclass(frozen=True)
class HookDecision:
    """Final decision emitted by runner to Antigravity CLI."""

    decision: str = "allow"
    reason: Optional[str] = None
    data: Mapping[str, Any] = field(default_factory=lambda: MappingProxyType({}))
