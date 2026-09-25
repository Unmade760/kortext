#!/usr/bin/env python3
"""
Indexes codebase AST symbols and references directly into FalkorDB 'cerebrum_symbols'.
"""

import os
import sys
from pathlib import Path

# Ensure project root is in sys.path
sys.path.insert(0, "/Users/rb/cortex")

from cerebrum.chunking.ast_splitter import ASTCodeSplitter
from cerebrum.chunking.languages import LANG_MAP
from cerebrum.symbols.graph import SymbolGraphManager

SYMBOLS_GRAPH = os.getenv("FALKORDB_SYMBOLS_GRAPH", "cerebrum_symbols")


def index_directory(target_dir: str):
    root_path = Path(target_dir).resolve()
    print(f"[Cerebrum Indexer] Target: {root_path} -> Graph: {SYMBOLS_GRAPH}")
    manager = SymbolGraphManager(graph_name=SYMBOLS_GRAPH)

    total_files = 0
    total_decls = 0
    total_refs = 0

    for file_path in root_path.rglob("*"):
        if not file_path.is_file():
            continue
        # Skip pycache and hidden files
        if any(part.startswith(".") or part == "__pycache__" for part in file_path.parts):
            continue

        ext = file_path.suffix.lower()
        if ext not in LANG_MAP:
            continue

        try:
            content = file_path.read_text(encoding="utf-8", errors="replace")
            splitter = ASTCodeSplitter(language=LANG_MAP[ext])
            res = splitter.extract_symbols_and_references(content, file_path=str(file_path))
            manager.save_file_ast(
                str(file_path),
                res["declarations"],
                res["imports"],
                res["references"]
            )
            total_files += 1
            total_decls += len(res["declarations"])
            total_refs += len(res["references"])
            print(f"  Indexed {file_path.relative_to(root_path.parent)}: {len(res['declarations'])} decls, {len(res['references'])} refs")
        except Exception as e:
            print(f"  [Error] Failed to index {file_path}: {e}", file=sys.stderr)

    print(f"\n[Cerebrum Indexer] Completed! Indexed {total_files} files, {total_decls} declarations, {total_refs} references.")
    stats = manager.get_statistics()
    print(f"[Cerebrum Indexer] FalkorDB Statistics for '{SYMBOLS_GRAPH}': {stats}")


if __name__ == "__main__":
    target = sys.argv[1] if len(sys.argv) > 1 else "/Users/rb/cortex/cerebrum"
    index_directory(target)
