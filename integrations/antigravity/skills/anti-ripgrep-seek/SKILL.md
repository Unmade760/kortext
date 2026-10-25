---
name: anti-ripgrep-seek
description: Use when locating code symbols, class or function definitions, call graphs, imports, or refactoring blast radiuses to avoid ripgrep/grep token bleed.
---

# Anti-Ripgrep Symbol Navigation Protocol

Enforces deterministic, compiler-grade AST code navigation via Kortext's FalkorDB symbol graph (`kortext_symbols`). Never use brute-force text search (`grep`, `rg`) to locate symbol declarations, class hierarchies, or call sites.

## 1. Token & Latency Economics

| Method | Substrate | Latency | Token Cost | Precision | Failure Mode |
|---|---|---|---|---|---|
| `grep` / `rg` | Filesystem regex | 100–800ms | 2,000–15,000 tokens | Low | Matches comments, strings, fixtures; blows up context |
| `seek_symbol` | FalkorDB Tier 0 AST B-Tree | **<2ms** | **50–150 tokens** | **100% (AST)** | None (returns exact file, signature, and line span) |
| `trace_symbol_impact` | FalkorDB `CALLS`/`REFERENCES` graph | **<10ms** | **200–800 tokens** | **100% (Graph)** | None (Knapsack-bounded caller/callee closure) |
| `search_knowledge_and_memory` | 5-Tier Hybrid RAG | 50–150ms | 500–1,500 tokens | Semantic + AST | Use only when exact symbol identifier is unknown |

## 2. Tool Selection Decision Matrix

| Navigation Intent | Primary Tool | Exact Call Pattern |
|---|---|---|
| Jump to class, function, or method definition (skeleton/signature) | `seek_symbol` | `seek_symbol(symbol_name="TokenCounter", detail_level="skeleton")` |
| Read full function implementation directly from AST index | `seek_symbol` | `seek_symbol(symbol_name="TokenCounter", detail_level="full")` |
| Disambiguate common method name (`execute`, `run`, `init`) | `seek_symbol` | `seek_symbol(symbol_name="execute", file_hint="task_runner.py")` |
| Find all upstream callers before changing a signature | `trace_symbol_impact` | `trace_symbol_impact(symbol="CausalSanitizer", direction="upstream", max_depth=3)` |
| Inspect downstream dependencies a symbol calls | `trace_symbol_impact` | `trace_symbol_impact(symbol="ContextPacker", direction="downstream", max_depth=2)` |
| Discover architecture or feature logic when symbol name is unknown | `search_knowledge_and_memory` | `search_knowledge_and_memory(query="bi-temporal fact invalidation", collection="kortext_codebase")` |
| Search non-AST literal string (env var name, raw error string, config key) | `grep_search` / `rg` | **Permitted exception ONLY for non-AST string literals** |

## 3. Deterministic 3-Step Navigation Pipeline

1. **Seek Declaration (`<2ms`)**:
   ```python
   sym = seek_symbol(symbol_name="RetrievalEngine", detail_level="skeleton")
   # Returns: file, line_start, line_end, signature, docstring
   ```
2. **Trace Blast Radius (`<10ms`)**:
   ```python
   impact = trace_symbol_impact(symbol="RetrievalEngine", direction="upstream", max_depth=2, token_budget=1200)
   # Returns: 1-hop full caller signatures, 2-hop file paths, 3+ hop transitive counts
   ```
3. **Surgical File Read (`<500` tokens)**:
   ```python
   view_file(AbsolutePath=sym["file"], StartLine=sym["line_start"], EndLine=sym["line_end"])
   ```

## 4. Rationalization Defense Table

| Common Excuse | Why It Fails | Required Action |
|---|---|---|
| *"Running `rg 'def my_func'` is faster than calling an MCP tool."* | `rg` scans hundreds of files and dumps test mocks and comments into context; `seek_symbol` is an O(1) B-Tree lookup (`<2ms`). | Always call `seek_symbol(symbol_name="my_func")`. |
| *"I'll read the whole 900-line file so I don't miss anything."* | Full-file reads waste 3,000+ tokens and degrade attention over long sessions. | Use `seek_symbol` line bounds + `view_file(StartLine=..., EndLine=...)`. |
| *"I only renamed an optional parameter, no need to check callers."* | Positional callers and subclass overrides break silently without graph inspection. | Always run `trace_symbol_impact(..., direction="upstream")` before and after signature edits. |
