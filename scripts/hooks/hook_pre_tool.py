#!/usr/bin/env python3
"""
Antigravity PreToolUse Hook (thin wrapper delegating to kortext.hooks.runner).
"""
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from kortext.hooks.context import HookContext
from kortext.hooks.runner import emit_response, run_hook


def main() -> None:
    ctx = HookContext.from_stdin(event="pre_tool")
    res = run_hook("pre_tool", ctx)
    emit_response(event="pre_tool", decision=res.decision, reason=res.reason, data=res.data)


if __name__ == "__main__":
    main()
