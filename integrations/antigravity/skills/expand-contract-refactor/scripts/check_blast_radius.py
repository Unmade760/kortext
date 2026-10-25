#!/usr/bin/env python3
"""
Black-box blast-radius analyzer for `expand-contract-refactor` skill.
Queries Kortext's SymbolSeekEngine and SymbolGraphManager to classify a symbol into
Tier 1 (Isolated), Tier 2 (Local), Tier 3 (Subsystem), or Tier 4 (Core/Schema).
Usage:
  python3 check_blast_radius.py <SymbolName> [--depth 3]
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

REPO_ROOT = Path(__file__).resolve().parents[5]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))


def main() -> None:
    parser = argparse.ArgumentParser(description="Compute AST refactoring blast tier for a symbol.")
    parser.add_argument("symbol", help="Target symbol name (e.g. RetrievalEngine)")
    parser.add_argument("--depth", type=int, default=3, help="Max traversal depth (default: 3)")
    args = parser.parse_args()

    from kortext.symbols.graph import SymbolGraphManager
    from kortext.symbols.seek import SymbolSeekEngine

    seeker = SymbolSeekEngine()
    seek_res = json.loads(seeker.seek_symbol(args.symbol, detail_level="skeleton"))
    mgr = SymbolGraphManager()
    impact = mgr.trace_symbol_impact(args.symbol, direction="upstream", max_depth=args.depth, token_budget=1500)

    hop1 = impact.get("hop_1_callers") or impact.get("upstream_callers") or []
    hop2 = impact.get("hop_2_files") or []
    caller_count = len(hop1)
    file_count = len({c.get("file") for c in hop1 if isinstance(c, dict) and c.get("file")} | set(hop2))

    if caller_count == 0 and file_count <= 1:
        tier = "Tier 1: Isolated (Direct atomic edit)"
    elif caller_count <= 5 and file_count <= 3:
        tier = "Tier 2: Local (Single-commit coordinated update)"
    elif caller_count <= 20 and file_count <= 10:
        tier = "Tier 3: Subsystem (Task DAG + 3-Phase Expand-Contract)"
    else:
        tier = "Tier 4: Core / Schema (ADR + Batched Expand-Contract + Dream Audit)"

    out = {
        "symbol": args.symbol,
        "blast_tier": tier,
        "upstream_callers_count": caller_count,
        "affected_files_count": file_count,
        "declarations": seek_res.get("matches", [])[:3],
        "impact": impact,
    }
    print(json.dumps(out, indent=2))


if __name__ == "__main__":
    main()
