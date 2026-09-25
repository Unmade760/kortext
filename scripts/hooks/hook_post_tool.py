#!/usr/bin/env python3
"""
Cerebrum PostToolUse Hook: Safe spool-based cache invalidation.
Lifecycle hooks NEVER instantiate QdrantClient or write directly to SQLite
to prevent exclusive OS lock crashes (RocksDB LOCK_EX).
"""
import json
import os
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from common import emit_hook_response, get_hook_payload

FILE_MODIFYING_TOOLS = {
    "write_to_file",
    "replace_file_content",
    "multi_replace_file_content",
}


def main():
    payload = get_hook_payload()
    tool_call = payload.get("toolCall", {})
    name = tool_call.get("name", "")
    args = tool_call.get("args", {}) or {}

    if name in FILE_MODIFYING_TOOLS:
        target_file = args.get("TargetFile")
        if target_file and os.path.isfile(target_file):
            spool_dir = Path.home() / ".cerebrum" / "spool" / "invalidation"
            try:
                spool_dir.mkdir(parents=True, exist_ok=True)
                event_file = spool_dir / f"event_{os.getpid()}_{int(time.time() * 1000)}.json"
                event_file.write_text(json.dumps({"action": "invalidate", "path": target_file}))
            except Exception:
                pass

    emit_hook_response({})


if __name__ == "__main__":
    main()
