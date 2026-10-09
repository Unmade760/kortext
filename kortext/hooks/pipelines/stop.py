"""
Stop pipeline: Task DAG readiness verification, unpersisted modification gating,
test verification gate, and MINJA causal memory fact sanitization.
"""

from __future__ import annotations

import json
import logging
import os
import sys
from types import MappingProxyType
from typing import Any, Dict, List, Optional, Sequence, Tuple

from kortext.hooks.context import HookContext
from kortext.hooks.types import InterceptorResult

logger = logging.getLogger("kortext.hooks.pipelines.stop")

FILE_MODIFYING_TOOLS = frozenset({
    "write_to_file",
    "replace_file_content",
    "multi_replace_file_content",
})

OUTCOME_TOOLS = frozenset({
    "record_system_outcome",
    "trigger_dream_mode",
})


def _analyze_transcript_outcomes(context: HookContext) -> Tuple[bool, bool]:
    """
    Scans transcript steps to verify whether files were modified and
    whether record_system_outcome or trigger_dream_mode was executed.
    """
    steps = context.read_transcript_steps()
    if not steps:
        return False, True

    modified_files = False
    recorded_outcome = False

    for step in steps:
        tool_calls = step.get("tool_calls")
        if isinstance(tool_calls, (list, tuple)):
            for tc in tool_calls:
                if not isinstance(tc, (dict, MappingProxyType)):
                    continue
                name = str(tc.get("name") or tc.get("tool_name") or "")
                args = tc.get("args") or {}

                # Check outcome tools
                if any(ot in name for ot in OUTCOME_TOOLS):
                    recorded_outcome = True
                elif isinstance(args, (dict, MappingProxyType)):
                    target_tool = str(args.get("ToolName", ""))
                    if any(ot == target_tool for ot in OUTCOME_TOOLS):
                        recorded_outcome = True
                    elif name == "run_command" and any(ot in str(args.get("CommandLine", "")) for ot in OUTCOME_TOOLS):
                        recorded_outcome = True

                # Check modification tools
                if any(ft in name for ft in FILE_MODIFYING_TOOLS):
                    modified_files = True

    return modified_files, recorded_outcome


class GroundTruthTestGate:
    """
    Optional test verification gate ensuring tests ran before stopping.
    """

    def __init__(self, enforce: bool = False):
        self.enforce = enforce or os.getenv("KORTEXT_TEST_GATE_ENFORCE", "0") == "1"

    def process(self, context: HookContext) -> InterceptorResult:
        if not self.enforce:
            return InterceptorResult.allow()

        steps = context.read_transcript_steps()
        ran_tests = False
        for step in steps:
            for tc in step.get("tool_calls", ()):
                if isinstance(tc, (dict, MappingProxyType)):
                    name = tc.get("name") or ""
                    args = tc.get("args") or {}
                    if name == "run_command" and "pytest" in str(args.get("CommandLine", "")):
                        ran_tests = True
                        break

        if not ran_tests:
            return InterceptorResult.continue_execution(
                reason="🛑 [GroundTruthTestGate] Test enforcement active: You must execute test suite before stopping."
            )

        return InterceptorResult.allow()


class ProjectDAGGuard:
    """
    Verifies that no uncompleted ready tasks remain in the Task DAG before allowing termination.
    """

    def process(self, context: HookContext) -> InterceptorResult:
        # Only check on final model stop when system is idle
        if not context.fully_idle or (context.termination_reason and context.termination_reason != "model_stop"):
            return InterceptorResult.allow()

        try:
            from kortext.tasks.tracker import TaskDAGTracker

            tracker = TaskDAGTracker()
            ready_tasks = tracker.get_ready_tasks()
            if ready_tasks:
                task_list = ", ".join([f"{t.get('id')} ({t.get('title', '')})" for t in ready_tasks[:3]])
                reason = (
                    f"🛑 [Kortext DAG Gate] Execution cannot stop: Uncompleted ready tasks remain in DAG: {task_list}. "
                    "Please delegate or complete these tasks before terminating."
                )
                return InterceptorResult.continue_execution(
                    reason=reason,
                    data=MappingProxyType({"ready_tasks": tuple(ready_tasks)}),
                )
        except Exception as e:
            logger.debug("ProjectDAGGuard bypassed due to: %s", e)

        return InterceptorResult.allow()


class OutcomePersistenceGuard:
    """
    Ensures modified files are accompanied by record_system_outcome persistence before stop.
    """

    def process(self, context: HookContext) -> InterceptorResult:
        if not context.fully_idle:
            return InterceptorResult.allow()

        modified_files, recorded_outcome = _analyze_transcript_outcomes(context)
        if modified_files and not recorded_outcome:
            reason = (
                "🧠 [Kortext Stop Guard] Codebase files were modified in this session without "
                "recording an outcome. Please call `record_system_outcome` to persist your decisions, "
                "changes, and verified behavior into Kortext memory before finishing."
            )
            return InterceptorResult.continue_execution(reason=reason)

        return InterceptorResult.allow()


class MINJAFactSanitizer:
    """
    Sanitizes candidate learned facts with CausalSanitizer before memory graph ingestion.
    """

    def process(self, context: HookContext) -> InterceptorResult:
        raw_facts: List[Dict[str, Any]] = []

        # Extract from payload
        payload = context.raw_payload
        for k in ("learned_facts", "facts"):
            val = payload.get(k)
            if isinstance(val, (list, tuple)):
                for item in val:
                    if isinstance(item, (dict, MappingProxyType)):
                        raw_facts.append(dict(item))
                    elif isinstance(item, str):
                        raw_facts.append({
                            "subject": "Session",
                            "relation": "LEARNED",
                            "fact": item,
                            "source_tier": 2,
                        })

        if not raw_facts:
            return InterceptorResult.allow(data=MappingProxyType({"sanitized_facts": ()}))

        # Sanitize with CausalSanitizer
        sanitized: List[Dict[str, Any]] = []
        try:
            from kortext.trust.sanitizer import CausalSanitizer

            sanitizer = CausalSanitizer()
            for f in raw_facts:
                sub = str(f.get("subject") or f.get("source") or "Session")
                rel = str(f.get("relation") or "LEARNED")
                fact_text = str(f.get("fact") or f.get("target") or "")
                tier = int(f.get("source_tier", 2))

                try:
                    sanitizer.sanitize(subject=sub, relation=rel, fact=fact_text, source_tier=tier)
                    sanitized.append(f)
                except Exception as exc:
                    logger.warning("[MINJAFactSanitizer] Fact blocked by CausalSanitizer: %s", exc)
                    continue
        except Exception as e:
            logger.debug("CausalSanitizer import/execution bypassed: %s", e)
            sanitized = raw_facts

        return InterceptorResult.allow(data=MappingProxyType({"sanitized_facts": tuple(sanitized)}))


class StopPipeline:
    """Dispatches Stop interceptors sequentially."""

    def __init__(self, interceptors: Optional[Sequence[Any]] = None):
        self.interceptors = tuple(interceptors) if interceptors is not None else (
            GroundTruthTestGate(),
            ProjectDAGGuard(),
            OutcomePersistenceGuard(),
            MINJAFactSanitizer(),
        )

    def execute(self, context: HookContext) -> InterceptorResult:
        merged_data: Dict[str, Any] = {}
        for interceptor in self.interceptors:
            try:
                res = interceptor.process(context)
                if res.decision == "continue":
                    return res
                if res.data:
                    for k, v in res.data.items():
                        merged_data[k] = v
            except Exception as e:
                logger.debug("Stop interceptor %s failed: %s", type(interceptor).__name__, e)
                continue

        return InterceptorResult.stop(data=MappingProxyType(merged_data))
