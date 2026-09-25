---
name: anti-ripgrep-seek
description: Operational protocol for deterministically locating code symbols, call graphs, and blast radiuses without ripgrep token bleed.
version: 2.0.0
triggers:
  - "find symbol"
  - "where is defined"
  - "who calls"
  - "blast radius"
---

# Anti-Ripgrep Symbol Navigation Runbook

## Protocol Steps:
1. **Exact Symbol Declaration:**
   - Call `seek_symbol(symbol_name="<TargetName>")`.
   - Inspect returned `signature`, `file`, and `lines`.
   - Never grep the workspace text.
2. **Blast Radius Assessment:**
   - If planning to modify parameters or return types, call `trace_symbol_impact(symbol_name="<TargetName>", depth=2)`.
   - Identify all upstream callers across the returned `affected_files`.
3. **Exploratory Fuzzy Search:**
   - If exact identifier is unknown, call `search_knowledge_and_memory(query="<intent>", include_code_symbols=True)`.
   - Inspect high-density Knapsack-packed symbol slices.
