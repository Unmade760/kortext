#!/usr/bin/env python3
"""
Cerebrum PreToolUse Hook: Safety gating for dangerous shell commands and AST complexity audit.
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from common import emit_hook_response, get_hook_payload

DANGEROUS_COMMANDS = [
    r"\brm\s+-[a-zA-Z]*r[a-zA-Z]*f\s+[/~]",
    r"\bgit\s+reset\s+--hard\b",
    r"\bdrop\s+database\b",
    r"\bformat\s+c:",
    r":\(\)\s*\{\s*:\|:&\s*\};:",
]

CORE_ARCHITECTURAL_FILES = {
    "server.py", "graph.py", "engine.py", "driver.py", "dream.py"
}


def main():
    payload = get_hook_payload()
    tool_call = payload.get("toolCall", {})
    name = tool_call.get("name", "")
    args = tool_call.get("args", {}) or {}

    # Safety Gate for run_command
    if name == "run_command":
        cmd = args.get("CommandLine", "").strip()
        for dangerous in DANGEROUS_COMMANDS:
            if re.search(dangerous, cmd, re.IGNORECASE):
                emit_hook_response({
                    "decision": "deny",
                    "reason": f"Execution blocked: Command contains forbidden dangerous pattern '{dangerous}'."
                })
                return

        # Anti-Ripgrep Reminder
        lower_cmd = cmd.lower()
        if lower_cmd.startswith("rg ") or "grep " in lower_cmd:
            if not any(f in lower_cmd for f in ("pytest", "log", "journal", "curl")):
                emit_hook_response({
                    "decision": "allow",
                    "reason": "Tip: Use `seek_symbol` for exact code navigation to save context tokens."
                })
                return

    elif name in ("write_to_file", "replace_file_content", "multi_replace_file_content"):
        target_file = args.get("TargetFile", "")
        file_name = target_file.split("/")[-1]
        if file_name in CORE_ARCHITECTURAL_FILES and "cerebrum/cerebrum/" in target_file:
            print(f"[Cerebrum PreTool] ℹ️ Modifying core architectural file {file_name}. Ensure trace_symbol_impact was run.", file=sys.stderr)

    emit_hook_response({"decision": "allow"})


if __name__ == "__main__":
    main()
