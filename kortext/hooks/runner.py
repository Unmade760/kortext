"""
CLI runner and dispatcher for Antigravity lifecycle hooks.
"""

from __future__ import annotations

import json
import logging
import sys
from types import MappingProxyType
from typing import Any, Mapping, Optional

from kortext.hooks.context import HookContext
from kortext.hooks.pipelines.post_invoke import PostInvokePipeline
from kortext.hooks.pipelines.post_tool import PostToolPipeline
from kortext.hooks.pipelines.pre_invoke import PreInvokePipeline
from kortext.hooks.pipelines.pre_tool import PreToolPipeline
from kortext.hooks.pipelines.stop import StopPipeline
from kortext.hooks.types import InterceptorResult

logger = logging.getLogger("kortext.hooks.runner")


def emit_response(
    event: str = "",
    decision: str = "allow",
    reason: Optional[str] = None,
    data: Optional[Mapping[str, Any]] = None,
) -> None:
    """
    Serializes hook response dictionary to stdout and flushes.
    PostToolUse and PostInvocation proto schemas do not accept 'decision' field.
    """
    output: dict[str, Any] = {}
    ev = event.lower().strip()
    if ev in ("pre_tool", "stop", ""):
        output["decision"] = decision
        if reason is not None:
            output["reason"] = reason
    if data:
        for k, v in data.items():
            output[k] = v
    sys.stdout.write(json.dumps(output))
    sys.stdout.flush()


def run_hook(event: str, context: Optional[HookContext] = None) -> InterceptorResult:
    """
    Dispatches hook context to the corresponding pipeline.
    """
    ctx = context if context is not None else HookContext.from_stdin(event=event)

    ev = event.lower().strip()
    if ev == "pre_tool":
        pipeline = PreToolPipeline()
        return pipeline.execute(ctx)
    elif ev == "post_tool":
        pipeline = PostToolPipeline()
        return pipeline.execute(ctx)
    elif ev == "pre_invoke":
        pipeline = PreInvokePipeline()
        return pipeline.execute(ctx)
    elif ev == "post_invoke":
        pipeline = PostInvokePipeline()
        return pipeline.execute(ctx)
    elif ev == "stop":
        pipeline = StopPipeline()
        return pipeline.execute(ctx)
    else:
        logger.debug("Unknown hook event '%s', defaulting to allow", event)
        return InterceptorResult.allow()


def main() -> None:
    """
    Main CLI entry point for lifecycle hooks: python3 -m kortext.hooks.runner <event>
    """
    target_event = "pre_tool"
    try:
        event = sys.argv[1] if len(sys.argv) > 1 else ""
        context = HookContext.from_stdin(event=event)
        target_event = event or context.event or "pre_tool"

        result = run_hook(target_event, context)
        emit_response(
            event=target_event,
            decision=result.decision,
            reason=result.reason,
            data=result.data,
        )
    except Exception as exc:
        # Failsafe: lifecycle hooks must never crash Antigravity background turns
        print(f"[KortextHooks] Runner encountered unexpected error: {exc}", file=sys.stderr)
        emit_response(event=target_event, decision="allow")


if __name__ == "__main__":
    main()
