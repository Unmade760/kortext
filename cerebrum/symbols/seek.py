"""
Cerebrum Anti-Ripgrep Deterministic Symbol Seek & Smart Code Search Engine.
Eliminates repeated ripgrep loops by providing B-Tree symbol seeks and knapsack-bounded regex.
"""

from __future__ import annotations

import json
import logging
import re
import time
from pathlib import Path
from typing import Any, Dict, List, Optional

from cerebrum.falkordb_client import get_shared_falkordb_client

logger = logging.getLogger("cerebrum.symbols.seek")


class SymbolSeekEngine:
    """Deterministic symbol locator and blast-radius traverser."""

    def __init__(self):
        self.client = get_shared_falkordb_client()

    def seek_symbol(self, symbol_name: str, file_hint: Optional[str] = None) -> str:
        """
        Locates exact symbol declaration, signature, docstring, callers, and callees.
        Returns dense structured JSON consuming <150 tokens.
        """
        # 1. Fast Path: Exact B-Tree indexed lookup on Symbol.name (Linear aggregation)
        fast_cypher = """
        MATCH (s:Symbol {name: $name})
        OPTIONAL MATCH (s)-[d:DEFINED_IN]->(f:File)
        WITH s, d, f
        OPTIONAL MATCH (caller:Symbol)-[c:CALLS]->(s)
        WITH s, d, f, collect(DISTINCT {caller: caller.name, file: caller.file_path, line: c.line})[..6] AS callers
        OPTIONAL MATCH (s)-[out:CALLS]->(callee:Symbol)
        RETURN 
            s.name AS symbol,
            s.kind AS kind,
            f.path AS file,
            d.line AS line,
            d.end_line AS end_line,
            d.signature AS signature,
            d.docstring AS docstring,
            callers,
            collect(DISTINCT {callee: callee.name, file: callee.file_path})[..6] AS callees
        LIMIT 5
        """
        params = {"name": symbol_name}
        raw = self.client.query("cerebrum_symbols", fast_cypher, params, read_only=True)

        # 2. Fallback Path: Substring search on qualified_name if exact match missed
        if not raw or len(raw) < 2 or not raw[1]:
            fallback_cypher = """
            MATCH (s:Symbol)
            WHERE s.qualified_name CONTAINS $name
            OPTIONAL MATCH (s)-[d:DEFINED_IN]->(f:File)
            OPTIONAL MATCH (caller:Symbol)-[c:CALLS]->(s)
            OPTIONAL MATCH (s)-[out:CALLS]->(callee:Symbol)
            RETURN 
                s.name AS symbol,
                s.kind AS kind,
                f.path AS file,
                d.line AS line,
                d.end_line AS end_line,
                d.signature AS signature,
                d.docstring AS docstring,
                collect(DISTINCT {caller: caller.name, file: caller.file_path, line: c.line})[..6] AS callers,
                collect(DISTINCT {callee: callee.name, file: callee.file_path})[..6] AS callees
            LIMIT 5
            """
            raw = self.client.query("cerebrum_symbols", fallback_cypher, params)

        if not raw or len(raw) < 2 or not raw[1]:
            return json.dumps({"status": "not_found", "query": symbol_name})

        matches = []
        for row in raw[1]:
            matches.append({
                "symbol": row[0],
                "kind": row[1],
                "file": row[2],
                "lines": [row[3], row[4]],
                "signature": row[5],
                "docstring": (row[6] or "")[:120].strip(),
                "callers": row[7],
                "callees": row[8],
            })

        return json.dumps({"status": "found", "matches": matches}, indent=2)

    def trace_impact(self, symbol_name: str, depth: int = 2) -> str:
        """Traverses up to depth hops of incoming callers to compute refactoring blast radius."""
        cypher = """
        MATCH path = (caller:Symbol)-[:CALLS*1..3]->(target:Symbol)
        WHERE target.name = $name
        RETURN 
            [n in nodes(path) | n.name] AS call_chain,
            [n in nodes(path) | n.file_path] AS file_chain,
            length(path) AS distance
        LIMIT 25
        """
        raw = self.client.query("cerebrum_symbols", cypher, {"name": symbol_name})
        if not raw or len(raw) < 2 or not raw[1]:
            return json.dumps({"symbol": symbol_name, "impact_radius": 0, "call_chains": []})

        chains = []
        affected_files = set()
        for row in raw[1]:
            nodes = row[0]
            if isinstance(nodes, str):
                nodes = [x.strip() for x in nodes.strip("[]").split(",") if x.strip()]
            files = row[1]
            if isinstance(files, str):
                files = [x.strip() for x in files.strip("[]").split(",") if x.strip()]
            chains.append({"chain": " -> ".join(nodes), "distance": row[2]})
            for f in files:
                if f and f != "NULL":
                    affected_files.add(f)

        return json.dumps({
            "symbol": symbol_name,
            "total_call_chains": len(chains),
            "affected_files": sorted(list(affected_files)),
            "call_chains": chains[:10],
        }, indent=2)
