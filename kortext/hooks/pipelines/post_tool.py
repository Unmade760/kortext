"""
Post-tool interceptor pipeline: Incremental AST synchronization and telemetry spooling.
"""

from __future__ import annotations

import json
import logging
import os
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from types import MappingProxyType
from typing import Any, Optional, Sequence

from kortext._home import get_kortext_home
from kortext.hooks.context import HookContext
from kortext.hooks.types import InterceptorResult

logger = logging.getLogger("kortext.hooks.pipelines.post_tool")

FILE_MODIFYING_TOOLS = frozenset({
    "write_to_file",
    "replace_file_content",
    "multi_replace_file_content",
})


class IncrementalASTSync:
    """
    Performs fast incremental AST index synchronization or spools invalidation events
    for modified Python and codebase files.
    """

    def __init__(self, spool_dir: Optional[Path] = None, sync_ast: bool = False):
        if spool_dir is not None:
            self.spool_dir = spool_dir
        else:
            self.spool_dir = get_kortext_home() / "spool" / "invalidation"
        self.sync_ast = sync_ast

    def process(self, context: HookContext) -> InterceptorResult:
        if context.tool_name not in FILE_MODIFYING_TOOLS:
            return InterceptorResult.allow()

        target_file = context.target_file
        if not target_file or not os.path.isfile(target_file):
            return InterceptorResult.allow()

        # 1. Spool invalidation event for background watcher/indexer
        try:
            self.spool_dir.mkdir(parents=True, exist_ok=True)
            event_file = self.spool_dir / f"event_{os.getpid()}_{int(time.time() * 1000)}.json"
            event_payload = {
                "action": "invalidate",
                "path": target_file,
                "timestamp": datetime.now(timezone.utc).isoformat(),
            }
            event_file.write_text(json.dumps(event_payload), encoding="utf-8")
        except Exception as e:
            logger.debug("Failed spooling invalidation event: %s", e)

        # 2. Fast AST direct sync if requested and target is Python
        if self.sync_ast and target_file.endswith(".py"):
            try:
                from kortext.chunking.ast_splitter import ASTCodeSplitter
                from kortext.symbols.graph import SymbolGraphManager

                content = Path(target_file).read_text(encoding="utf-8")
                splitter = ASTCodeSplitter(language="python")
                ast_info = splitter.extract_symbols_and_references(content, file_path=target_file)
                decls = ast_info.get("declarations", [])
                imports = ast_info.get("imports", [])
                refs = ast_info.get("references", [])

                mgr = SymbolGraphManager()
                mgr.save_file_ast(
                    file_path=target_file,
                    declarations=decls,
                    imports=imports,
                    references=refs,
                )
            except Exception as e:
                logger.debug("Direct AST sync fallback safely caught: %s", e)

        return InterceptorResult.allow()


class TelemetrySpooler:
    """
    Spools non-blocking tool execution metrics and latency telemetry to disk.
    """

    def __init__(self, telemetry_dir: Optional[Path] = None):
        if telemetry_dir is not None:
            self.telemetry_dir = telemetry_dir
        else:
            self.telemetry_dir = get_kortext_home() / "telemetry"

    def process(self, context: HookContext) -> InterceptorResult:
        try:
            self.telemetry_dir.mkdir(parents=True, exist_ok=True)
            log_file = self.telemetry_dir / "tools.jsonl"
            entry = {
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "session_id": context.session_id,
                "turn_index": context.turn_index,
                "tool_name": context.tool_name,
                "target_file": context.target_file if context.target_file else None,
                "command": context.command_line if context.command_line else None,
            }
            with open(log_file, "a", encoding="utf-8") as f:
                f.write(json.dumps(entry) + "\n")
        except Exception as e:
            logger.debug("Telemetry logging failed: %s", e)

        return InterceptorResult.allow()


class PostToolPipeline:
    """Dispatches PostToolUse interceptors sequentially."""

    def __init__(self, interceptors: Optional[Sequence[Any]] = None):
        self.interceptors = tuple(interceptors) if interceptors is not None else (
            IncrementalASTSync(),
            TelemetrySpooler(),
        )

    def execute(self, context: HookContext) -> InterceptorResult:
        for interceptor in self.interceptors:
            try:
                interceptor.process(context)
            except Exception as e:
                logger.debug("PostTool interceptor %s failed: %s", type(interceptor).__name__, e)
                continue

        return InterceptorResult.allow()
