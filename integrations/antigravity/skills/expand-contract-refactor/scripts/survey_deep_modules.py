#!/usr/bin/env python3
"""
Ousterhout Deep Module Architecture Survey Script (Matt Pocock /improve-codebase-architecture pattern).

Scans the FalkorDB `kortext_symbols` graph via `SubsystemClusterer.detect_shallow_modules()`
to identify shallow or high-coupling modules (high exported symbol count + cross-file callers
relative to symbol implementation depth) and outputs actionable consolidation candidates.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

REPO_ROOT = Path(__file__).resolve().parents[4]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Survey codebase symbol graph for shallow modules and consolidation opportunities."
    )
    parser.add_argument("--max-results", type=int, default=10, help="Maximum shallow module candidates to return")
    parser.add_argument("--graph", default="kortext_symbols", help="FalkorDB symbol graph name")
    parser.add_argument("--json", action="store_true", help="Output raw JSON")
    args = parser.parse_args()

    from kortext.symbols.clustering import SubsystemClusterer

    clusterer = SubsystemClusterer(graph_name=args.graph)
    candidates = clusterer.detect_shallow_modules(max_results=args.max_results)

    if args.json:
        print(json.dumps({"shallow_modules": candidates, "count": len(candidates)}, indent=2))
        return

    print("=== Kortext Deep-Module Architecture Survey ===")
    if not candidates:
        print("No shallow module hotspots detected (all modules meet depth thresholds).")
        return

    for idx, cand in enumerate(candidates, 1):
        print(
            f"{idx}. [{cand['module']}] {cand['file_path']}\n"
            f"   - Exported Symbols: {cand['exported_symbols']} | Avg Lines/Symbol: {cand['avg_lines_per_symbol']} "
            f"| External Caller Files: {cand['external_caller_files']} | Shallowness Score: {cand['shallowness_score']}\n"
            f"   - Recommendation: {cand['recommendation']}"
        )


if __name__ == "__main__":
    main()
