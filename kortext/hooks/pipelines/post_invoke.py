"""
Post-invocation pipeline: Runaway execution loop detection and token/turn telemetry tracking.
"""

from __future__ import annotations

import json
import logging
import sys
from datetime import datetime, timezone
from pathlib import Path
from types import MappingProxyType
from typing import Any, List, Optional, Sequence

from kortext._home import get_kortext_home
from kortext.hooks.context import HookContext
from kortext.hooks.types import InterceptorResult

logger = logging.getLogger("kortext.hooks.pipelines.post_invoke")


class RunawayExecutionGuard:
    """
    Detects repeated identical tool failures or error loops and trips a circuit breaker.
    """

    def __init__(self, max_identical_errors: int = 3):
        self.max_identical_errors = max_identical_errors

    def process(self, context: HookContext) -> InterceptorResult:
        steps = context.read_transcript_steps()
        if len(steps) < self.max_identical_errors:
            return InterceptorResult.allow()

        recent_errors: List[str] = []
        for step in reversed(steps):
            err_text = ""
            tool_res = step.get("tool_result")
            if isinstance(tool_res, (dict, MappingProxyType)):
                err_text = str(tool_res.get("error") or tool_res.get("stderr") or "").strip()
            elif isinstance(step.get("error"), str):
                err_text = str(step["error"]).strip()

            if err_text:
                recent_errors.append(err_text)
            else:
                # Sequence broken by non-error step
                break

            if len(recent_errors) >= self.max_identical_errors:
                break

        if len(recent_errors) >= self.max_identical_errors:
            # Check if all errors in this run are identical
            first_err = recent_errors[0]
            if all(e == first_err for e in recent_errors):
                reason = (
                    f"🛑 [Runaway Execution Guard] Detected identical repetitive error {len(recent_errors)} times "
                    f"in a row: '{first_err[:120]}...'. Circuit breaker tripped. "
                    "Analyze root cause systematically or reconsider approach rather than repeating the failing action."
                )
                print(reason, file=sys.stderr)
                return InterceptorResult.continue_execution(
                    reason=reason,
                    data=MappingProxyType({"repeated_error": first_err, "count": len(recent_errors)}),
                )

        return InterceptorResult.allow()


class TokenUsageTracker:
    """
    Tracks session turn telemetry and persists invocation metrics.
    """

    def __init__(self, telemetry_dir: Optional[Path] = None):
        self.telemetry_dir = telemetry_dir or (get_kortext_home() / "telemetry")

    def process(self, context: HookContext) -> InterceptorResult:
        try:
            self.telemetry_dir.mkdir(parents=True, exist_ok=True)
            log_file = self.telemetry_dir / "invocations.jsonl"
            steps = context.read_transcript_steps()
            record = {
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "session_id": context.session_id,
                "turn_index": context.turn_index,
                "step_count": len(steps),
            }
            with open(log_file, "a", encoding="utf-8") as f:
                f.write(json.dumps(record) + "\n")
        except Exception as e:
            logger.debug("Invocation telemetry logging failed: %s", e)

        return InterceptorResult.allow()


class PostInvokePipeline:
    """Dispatches PostInvocation interceptors sequentially."""

    def __init__(self, interceptors: Optional[Sequence[Any]] = None):
        self.interceptors = tuple(interceptors) if interceptors is not None else (
            RunawayExecutionGuard(),
            TokenUsageTracker(),
        )

    def execute(self, context: HookContext) -> InterceptorResult:
        for interceptor in self.interceptors:
            try:
                res = interceptor.process(context)
                if res.decision == "continue":
                    return res
            except Exception as e:
                logger.debug("PostInvoke interceptor %s failed: %s", type(interceptor).__name__, e)
                continue

        return InterceptorResult.allow()
