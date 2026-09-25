"""
Common utilities for Cerebrum Antigravity Lifecycle Hooks.
Provides non-blocking socket checks, JSON payload parsing, transcript analysis, and response formatting.
"""

from __future__ import annotations

import json
import os
import socket
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

# Automatically detect CEREBRUM_ROOT from script location
CEREBRUM_ROOT = Path(__file__).resolve().parent.parent.parent


def get_hook_payload() -> Dict[str, Any]:
    """Reads and parses JSON payload from stdin."""
    try:
        raw = sys.stdin.read().strip()
        if not raw:
            return {}
        return json.loads(raw)
    except Exception as e:
        print(f"[CerebrumHookError] Failed to parse stdin payload: {e}", file=sys.stderr)
        return {}


def emit_hook_response(response: Dict[str, Any]):
    """Outputs JSON response to stdout and exits cleanly."""
    sys.stdout.write(json.dumps(response))
    sys.stdout.flush()
    sys.exit(0)


def check_tcp_port(host: str, port: int, timeout_sec: float = 0.2) -> bool:
    """Performs a non-blocking TCP socket connect check."""
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
            sock.settimeout(timeout_sec)
            return sock.connect_ex((host, port)) == 0
    except Exception:
        return False


def check_unix_socket(socket_path: Path, timeout_sec: float = 0.2) -> bool:
    """Performs a non-blocking Unix Domain Socket connect check."""
    if not socket_path.is_socket():
        return False
    try:
        with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as sock:
            sock.settimeout(timeout_sec)
            sock.connect(str(socket_path))
            return True
    except Exception:
        return False


def analyze_transcript_modifications(transcript_path: str) -> Tuple[bool, bool]:
    """
    Scans transcript.jsonl to determine:
    1. Were any file-modifying tools executed?
    2. Was record_system_outcome or trigger_dream_mode executed?
    Never performs raw string matching on messages to avoid false positives from system banners.
    """
    if not transcript_path or not os.path.isfile(transcript_path):
        return False, True  # Fallback: don't block if transcript is inaccessible

    modified_files = False
    recorded_outcome = False

    file_tools = {"write_to_file", "replace_file_content", "multi_replace_file_content"}
    outcome_tools = {"record_system_outcome", "trigger_dream_mode"}

    try:
        with open(transcript_path, "r", encoding="utf-8", errors="replace") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    step = json.loads(line)
                except Exception:
                    continue

                tool_calls = step.get("tool_calls", [])
                if not isinstance(tool_calls, list):
                    continue

                for tc in tool_calls:
                    if not isinstance(tc, dict):
                        continue
                    name = tc.get("name") or tc.get("tool_name") or ""
                    args = tc.get("args", {}) or {}

                    for ot in outcome_tools:
                        if ot in name or (isinstance(args, dict) and ot in str(args)):
                            recorded_outcome = True

                    for ft in file_tools:
                        if ft in name:
                            modified_files = True

    except Exception as e:
        print(f"[CerebrumHookError] Transcript scan failed: {e}", file=sys.stderr)
        return False, True

    return modified_files, recorded_outcome
