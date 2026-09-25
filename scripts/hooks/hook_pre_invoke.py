#!/usr/bin/env python3
"""
Cerebrum PreInvocation Hook: Injects ambient symbol priming and enforces Task DAG delegation.
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from common import (
    CEREBRUM_ROOT,
    check_tcp_port,
    emit_hook_response,
    get_hook_payload,
)

INVARIANTS_FILE = CEREBRUM_ROOT / "journal" / "invariants.md"


def get_active_invariants(max_count: int = 3) -> list:
    if not INVARIANTS_FILE.is_file():
        return []
    try:
        text = INVARIANTS_FILE.read_text(encoding="utf-8")
        pattern = re.compile(
            r"###\s+Invariant\s+\[(.*?)\]\s*\n\*\*Rule:\*\*\s*(.*?)(?=\n\*\*Rationale:|\n###|\Z)",
            re.DOTALL,
        )
        invariants = []
        for match in pattern.finditer(text):
            topic = match.group(1).strip()
            rule = match.group(2).strip().replace("\n", " ")
            invariants.append(f"• **[{topic}]**: {rule}")
            if len(invariants) >= max_count:
                break
        return invariants
    except Exception:
        return []


def main():
    payload = get_hook_payload()
    invocation_num = payload.get("invocationNum", 0)

    # Ambient Service Health Check (FalkorDB: 6379, oMLX: 8000)
    services_up = {
        "FalkorDB": check_tcp_port("localhost", 6379),
        "oMLX": check_tcp_port("localhost", 8000),
    }

    down_services = [s for s, ok in services_up.items() if not ok]

    if down_services:
        message = (
            f"⚠️ [Cerebrum Health Alert] Offline services detected: {', '.join(down_services)}.\n"
            "Run `cerebrum start` to bring memory and inference substrates online."
        )
        emit_hook_response({"injectSteps": [{"ephemeralMessage": message}]})
        return

    # Turn 0: Ambient Grounding & Architectural Directives
    if invocation_num == 0:
        invariants = get_active_invariants(max_count=3)
        inv_str = "\n".join(invariants) if invariants else "• Invariants synchronized."
        message = (
            "🧠 [Cerebrum Cognitive OS Initialized]\n"
            "Active Protocols:\n"
            "1. ANTI-RIPGREP MANDATE: Do NOT run `rg` or `grep_search` to find symbols. Use `seek_symbol`.\n"
            "2. DELEGATION MANDATE: For multi-file changes (Complexity >= 4), initialize DAG via `manage_tasks`.\n"
            "3. PERSISTENCE MANDATE: Record outcomes via `record_system_outcome` before session stop.\n\n"
            f"Active Invariants:\n{inv_str}"
        )
        emit_hook_response({"injectSteps": [{"ephemeralMessage": message}]})
        return

    emit_hook_response({})


if __name__ == "__main__":
    main()
