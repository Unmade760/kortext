#!/usr/bin/env python3
"""
Cerebrum Stop Hook: Prevents premature termination if uncompleted ready tasks remain in DAG
or if files were modified without recording an outcome.
"""
from __future__ import annotations

import json
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from common import analyze_transcript_modifications, emit_hook_response, get_hook_payload


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
        from cerebrum.tasks.tracker import TaskDAGTracker
        tracker = TaskDAGTracker()
        ready_tasks = tracker.get_ready_tasks()
        if ready_tasks:
            task_list = ", ".join([f"{t['id']} ({t['title']})" for t in ready_tasks[:3]])
            reason = (
                f"🛑 [Cerebrum DAG Gate] Execution cannot stop: Uncompleted ready tasks remain in DAG: {task_list}. "
                "Please delegate or complete these tasks before terminating."
            )
            emit_hook_response({"decision": "continue", "reason": reason})
            return
    except Exception:
        pass

    # 2. Verify Outcome Persistence if files were modified
    modified_files, recorded_outcome = analyze_transcript_modifications(transcript_path)
    if modified_files and not recorded_outcome:
        emit_hook_response({
            "decision": "continue",
            "reason": (
                "🧠 [Cerebrum Stop Guard] Codebase files were modified in this session without "
                "recording an outcome. Please call `record_system_outcome` to persist your decisions, "
                "changes, and verified behavior into Cerebrum memory before finishing."
            )
        })
        return

    emit_hook_response({"decision": "stop"})


if __name__ == "__main__":
    main()
