#!/usr/bin/env python3
"""
Kortext Session & Hook Telemetry Diagnostic Script (Obra Superpowers diagnosing-superpowers pattern).

Inspects ~/.kortext/telemetry/tools.jsonl, ~/.kortext/run/hud_state.json,
~/.kortext/run/last_test_run.json, and ~/.kortext/quarantine/ to diagnose
hook denials, retry loops, compaction state, and substrate health.
"""
from __future__ import annotations

import argparse
from collections import Counter
import json
import os
from pathlib import Path
import sys
from typing import Any, Dict, List

REPO_ROOT = Path(__file__).resolve().parents[4]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))


def diagnose_kortext_session(tail_lines: int = 50) -> Dict[str, Any]:
    from kortext._home import get_kortext_home

    home = get_kortext_home()
    run_dir = home / "run"
    telemetry_file = home / "telemetry" / "tools.jsonl"
    quarantine_dir = home / "quarantine"

    hud_state: Dict[str, Any] = {}
    hud_file = run_dir / "hud_state.json"
    if hud_file.is_file():
        try:
            hud_state = json.loads(hud_file.read_text(encoding="utf-8"))
        except Exception:
            hud_state = {}

    last_test: Dict[str, Any] = {}
    test_file = run_dir / "last_test_run.json"
    if test_file.is_file():
        try:
            last_test = json.loads(test_file.read_text(encoding="utf-8"))
        except Exception:
            last_test = {}

    recent_events: List[Dict[str, Any]] = []
    tool_counts: Counter[str] = Counter()
    error_events: List[Dict[str, Any]] = []
    if telemetry_file.is_file():
        try:
            lines = telemetry_file.read_text(encoding="utf-8", errors="replace").splitlines()[-tail_lines:]
            for ln in lines:
                if not ln.strip():
                    continue
                ev = json.loads(ln)
                if isinstance(ev, dict):
                    recent_events.append(ev)
                    tname = str(ev.get("tool_name") or "unknown")
                    tool_counts[tname] += 1
                    if ev.get("error"):
                        error_events.append(ev)
        except Exception:
            pass

    quarantined_files = (
        sorted(str(p.name) for p in quarantine_dir.glob("*.json"))[-10:]
        if quarantine_dir.is_dir()
        else []
    )

    return {
        "kortext_home": str(home),
        "hook_profile": os.getenv("KORTEXT_HOOK_PROFILE", "standard"),
        "hud_state": hud_state,
        "last_test_run": last_test,
        "recent_tool_counts": dict(tool_counts.most_common(10)),
        "recent_error_count": len(error_events),
        "recent_errors": error_events[-5:],
        "quarantined_payloads": quarantined_files,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Diagnose Kortext session telemetry and hook state.")
    parser.add_argument("--tail", type=int, default=50, help="Number of recent tool telemetry events to inspect")
    parser.add_argument("--json", action="store_true", help="Output raw JSON")
    args = parser.parse_args()

    report = diagnose_kortext_session(tail_lines=args.tail)
    if args.json:
        print(json.dumps(report, indent=2))
        return

    print("=== Kortext Session Telemetry Diagnostics ===")
    print(f"  KORTEXT_HOME  : {report['kortext_home']}")
    print(f"  Hook Profile  : {report['hook_profile']}")
    hud = report.get("hud_state") or {}
    print(
        f"  Substrates    : FalkorDB={'OK' if hud.get('falkor_ok') else 'DOWN'} | "
        f"Qdrant={'OK' if hud.get('qdrant_ok') else 'DOWN'} | "
        f"DAG={hud.get('ready_tasks', 0)}r/{hud.get('in_progress_tasks', 0)}p | "
        f"Ctx={hud.get('used_percentage', 0.0):.1f}%"
    )
    print(f"  Recent Tools  : {report['recent_tool_counts']}")
    print(f"  Recent Errors : {report['recent_error_count']}")
    if report["quarantined_payloads"]:
        print(f"  Quarantined   : {report['quarantined_payloads']}")


if __name__ == "__main__":
    main()
