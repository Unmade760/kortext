"""
Kortext Hooks Package.
Provides lifecycle context, runner, and interceptor pipelines for Antigravity integration.
"""

from __future__ import annotations

from typing import Any, Mapping, Optional

from kortext.hooks.context import HookContext
from kortext.hooks.types import HookDecision, InterceptorResult


def emit_response(
    decision: str = "allow",
    reason: Optional[str] = None,
    data: Optional[Mapping[str, Any]] = None,
) -> None:
    """Lazy wrapper for runner.emit_response."""
    from kortext.hooks.runner import emit_response as _emit
    return _emit(decision=decision, reason=reason, data=data)


def run_hook(event: str, context: Optional[HookContext] = None) -> InterceptorResult:
    """Lazy wrapper for runner.run_hook."""
    from kortext.hooks.runner import run_hook as _run
    return _run(event=event, context=context)


__all__ = [
    "HookContext",
    "HookDecision",
    "InterceptorResult",
    "emit_response",
    "run_hook",
]
