#!/usr/bin/env python3
"""
Kortext PreInvocation Hook: Injects ambient symbol priming and enforces Task DAG delegation.
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from common import (
    KORTEXT_ROOT,
    check_http_health,
    check_tcp_port,
    check_unix_socket,
    emit_hook_response,
    get_hook_payload,
)

INVARIANTS_FILE = KORTEXT_ROOT / "journal" / "invariants.md"


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


def check_falkordb_status(timeout_sec: float = 0.2) -> bool:
    """Check FalkorDB UDS socket at ~/.kortext/run/falkordb.sock with TCP :6379 fallback."""
    falkor_sock = Path.home() / ".kortext" / "run" / "falkordb.sock"
    if check_unix_socket(falkor_sock, timeout_sec=timeout_sec):
        return True

    legacy_sock = Path.home() / ".cerebrum" / "run" / "falkordb.sock"
    if check_unix_socket(legacy_sock, timeout_sec=timeout_sec):
        return True

    return check_tcp_port("127.0.0.1", 6379, timeout_sec=timeout_sec) or check_tcp_port("localhost", 6379, timeout_sec=timeout_sec)


def check_qdrant_status(timeout_sec: float = 0.2) -> bool:
    """Check Qdrant HTTP health at :6333 using timeout of 0.2s."""
    return check_http_health("127.0.0.1", 6333, path="/healthz", timeout_sec=timeout_sec) or check_http_health("localhost", 6333, path="/healthz", timeout_sec=timeout_sec)


def main():
    payload = get_hook_payload()
    invocation_num = payload.get("invocationNum", 0)

    # Ambient Substrate Health Checks (FalkorDB UDS/TCP, Qdrant HTTP :6333)
    services_up = {
        "FalkorDB": check_falkordb_status(timeout_sec=0.2),
        "Qdrant": check_qdrant_status(timeout_sec=0.2),
    }

    down_services = [s for s, ok in services_up.items() if not ok]

    if down_services:
        message = (
            f"⚠️ [Kortext Health Alert] Offline services detected: {', '.join(down_services)}.\n"
            "Run `kortext start` to bring memory and inference substrates online."
        )
        print(message, file=sys.stderr)
        emit_hook_response({"injectSteps": [{"ephemeralMessage": message}]})
        return

    # Turn 0: Ambient Grounding & Architectural Directives
    if invocation_num == 0:
        invariants = get_active_invariants(max_count=3)
        inv_str = "\n".join(invariants) if invariants else "• Invariants synchronized."
        message = (
            "🧠 [Kortext Cognitive OS Initialized]\n"
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
