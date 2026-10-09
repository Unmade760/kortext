#!/usr/bin/env python3
"""
Kortext Stop Hook: Prevents premature termination if uncompleted ready tasks remain in DAG
or if files were modified without recording an outcome.
"""
from __future__ import annotations

import json
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from common import (
    analyze_transcript_modifications,
    emit_hook_response,
    get_hook_payload,
    read_transcript_steps,
)
from typing import Any, Dict, List, Optional


def extract_learned_facts_from_transcript(transcript_path: str) -> List[Dict[str, Any]]:
    """Extracts facts from transcript steps and tool calls."""
    steps = read_transcript_steps(transcript_path)
    facts: List[Dict[str, Any]] = []
    for step in steps:
        if not isinstance(step, dict):
            continue
        if "learned_facts" in step and isinstance(step["learned_facts"], list):
            facts.extend(step["learned_facts"])
        if "facts" in step and isinstance(step["facts"], list):
            facts.extend(step["facts"])
        tool_calls = step.get("tool_calls", [])
        if isinstance(tool_calls, list):
            for tc in tool_calls:
                if isinstance(tc, dict):
                    args = tc.get("args", {})
                    if isinstance(args, dict):
                        tc_facts = args.get("facts")
                        if isinstance(tc_facts, list):
                            facts.extend(tc_facts)
    return facts


def record_learned_facts(
    facts: List[Dict[str, Any]] | List[str],
    episode_name: str = "session_learned_facts",
    sanitizer: Any = None,
    driver: Any = None,
) -> List[Dict[str, Any]]:
    """
    Passes learned facts through CausalSanitizer before recording to episodic graph.
    Returns list of successfully sanitized and recorded facts.
    """
    if not facts:
        return []

    if sanitizer is None:
        try:
            from kortext.trust.sanitizer import CausalSanitizer
            sanitizer = CausalSanitizer()
        except ImportError:
            try:
                from cerebrum.trust.sanitizer import CausalSanitizer
                sanitizer = CausalSanitizer()
            except ImportError:
                sanitizer = None

    sanitized_facts: List[Dict[str, Any]] = []
    for item in facts:
        if isinstance(item, str):
            fact_dict = {"subject": "Session", "relation": "LEARNED", "fact": item, "source_tier": 2}
        elif isinstance(item, dict):
            fact_dict = dict(item)
        else:
            continue

        sub = fact_dict.get("subject") or fact_dict.get("source") or "Session"
        rel = fact_dict.get("relation") or "LEARNED"
        fact_text = fact_dict.get("fact") or fact_dict.get("target") or str(fact_dict)
        tier = fact_dict.get("source_tier", 2)

        if sanitizer:
            try:
                sanitizer.sanitize(subject=sub, relation=rel, fact=fact_text, source_tier=tier)
                sanitized_facts.append(fact_dict)
            except Exception as e:
                print(f"[KortextStopHook] Learned fact blocked by CausalSanitizer: {e}", file=sys.stderr)
                continue
        else:
            sanitized_facts.append(fact_dict)

    if sanitized_facts:
        if driver is None:
            try:
                from kortext.episodic.driver import AgentNativeEpisodicDriver
                driver = AgentNativeEpisodicDriver()
            except ImportError:
                try:
                    from cerebrum.episodic.driver import AgentNativeEpisodicDriver
                    driver = AgentNativeEpisodicDriver()
                except ImportError:
                    driver = None

        if driver is not None:
            for sf in sanitized_facts:
                sub = sf.get("subject") or sf.get("source") or "Session"
                rel = sf.get("relation") or "LEARNED"
                obj = sf.get("target") or sf.get("object") or rel
                fact_text = sf.get("fact") or str(sf)
                tier = sf.get("source_tier", 2)
                try:
                    driver.record_fact(
                        subject=sub,
                        relation=rel,
                        fact=fact_text,
                        object_name=obj,
                        source_session=episode_name,
                        source_tier=tier,
                    )
                except Exception as e:
                    print(f"[KortextStopHook] Error persisting fact: {e}", file=sys.stderr)

    return sanitized_facts


def main():
    payload = get_hook_payload()

    execution_num = payload.get("executionNum", 0)
    termination_reason = payload.get("terminationReason", "")
    transcript_path = payload.get("transcriptPath", "")
    fully_idle = payload.get("fullyIdle", True)

    # Only intervene on the first natural model stop
    if execution_num != 1 or termination_reason != "model_stop":
        emit_hook_response({"decision": "stop"})
        return

    # Don't block if background tasks are still running
    if not fully_idle:
        emit_hook_response({"decision": "stop"})
        return

    # 1. Verify Task DAG state
    try:
        try:
            from kortext.tasks.tracker import TaskDAGTracker
        except ImportError:
            from cerebrum.tasks.tracker import TaskDAGTracker
        tracker = TaskDAGTracker()
        ready_tasks = tracker.get_ready_tasks()
        if ready_tasks:
            task_list = ", ".join([f"{t['id']} ({t['title']})" for t in ready_tasks[:3]])
            reason = (
                f"🛑 [Kortext DAG Gate] Execution cannot stop: Uncompleted ready tasks remain in DAG: {task_list}. "
                "Please delegate or complete these tasks before terminating."
            )
            emit_hook_response({"decision": "continue", "reason": reason})
            return
    except Exception:
        pass

    # 2. Extract and record any learned facts (sanitized via CausalSanitizer)
    learned_facts = payload.get("learned_facts") or payload.get("facts") or []
    if transcript_path:
        learned_facts = list(learned_facts) + extract_learned_facts_from_transcript(transcript_path)
    if learned_facts:
        record_learned_facts(learned_facts)

    # 3. Verify Outcome Persistence if files were modified
    modified_files, recorded_outcome = analyze_transcript_modifications(transcript_path)
    if modified_files and not recorded_outcome:
        emit_hook_response({
            "decision": "continue",
            "reason": (
                "🧠 [Kortext Stop Guard] Codebase files were modified in this session without "
                "recording an outcome. Please call `record_system_outcome` to persist your decisions, "
                "changes, and verified behavior into Kortext memory before finishing."
            )
        })
        return

    emit_hook_response({"decision": "stop"})


if __name__ == "__main__":
    main()
