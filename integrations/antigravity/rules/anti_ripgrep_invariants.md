---
description: Mandatory rule prohibiting brute-force ripgrep text search in favor of deterministic AST symbol lookups.
globs: ["**/*"]
always_apply: true
---

# Invariant [Anti-Ripgrep-Mandate]

## Rule:
Agents MUST NEVER execute `ripgrep`, `rg`, or broad regex text scans (`grep_search`) to locate code declarations, symbol signatures, call sites, or interface dependencies.

Instead, agents MUST use the compiler-grade AST B-Tree index:
- **Locate exact symbol declaration & call hierarchy:** Call `seek_symbol(symbol_name="<symbol>")` (<2ms, <150 tokens).
- **Assess multi-hop refactoring impact:** Call `trace_symbol_impact(symbol="<symbol>", direction="upstream")` (<5ms).
- **Semantic associative concept search:** Call `search_knowledge_and_memory(query="<intent>")`.

## Rationale:
Unbounded ripgrep queries flood context windows with dozens of false-positive matches (12k+ tokens per turn), corrupting agent working memory, causing severe context fragmentation, and burning excessive token costs. AST B-Tree lookups guarantee deterministic precision with >95% token savings.
