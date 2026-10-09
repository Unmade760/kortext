---
name: anti-ripgrep-seek
description: Operational protocol for deterministically locating code symbols, call graphs, and blast radiuses without ripgrep token bleed.
version: 2.0.0
triggers:
  - "find symbol"
  - "where is defined"
  - "who calls"
  - "blast radius"
  - "anti-ripgrep"
  - "seek symbol"
license: MIT
metadata:
  origin: ECC
  adapted_for: Kortext
---

# Anti-Ripgrep Symbol Navigation Protocol

This skill enforces deterministic, AST-driven code navigation across Kortext codebases. It eliminates brute-force text search (`grep`, `rg`), prevents context window token bleed, and uses Kortext's FalkorDB knowledge graph to locate definitions, caller hierarchies, and blast radiuses with compiler-grade precision.

---

## The Core Invariant: AST-First Over Text Search

> **Never use text search (`grep`, `rg`) to locate symbol declarations, class hierarchies, or call sites.**

Brute-force text matching is non-deterministic: it returns irrelevant string literals, commented-out code, test fixtures, and docstring mentions. In large codebases, a single `grep` can flood the agent context with 5,000-15,000 tokens of noise, corrupting attention entropy and wasting context budget.

### Token & Latency Economics

| Method | Substrate / Mechanism | Latency | Typical Token Cost | Precision | Failure Modes |
|---|---|---|---|---|---|
| **`grep` / `rg`** | Text regex over filesystem | 100-800ms | 2,000-15,000 tokens | Low (matches text/comments) | Token bleed, false positives, misses qualified symbols |
| **`seek_symbol`** | FalkorDB Tier 0 AST B-Tree | **<2ms** | **50-150 tokens** | **100% (Compiler AST)** | None (exact declaration and line span) |
| **`trace_symbol_impact`** | FalkorDB graph walk (CALLS/REFERENCES) | **<10ms** | **200-800 tokens** | **100% (Graph Topology)** | None (complete caller/callee closure) |
| **`search_knowledge_and_memory`** | 5-Tier Hybrid (AST + Vector + HippoRAG) | 100-300ms | 500-1,500 tokens | Semantic & Structural | Concept drift if prompt is overly generic |

---

## Tool Selection Decision Matrix

```mermaid
flowchart TD
    Start[Navigation Intent] --> Q1{Do you know the exact symbol name?}
    Q1 -->|Yes| Q2{What information do you need?}
    Q1 -->|No| Q3{Are you searching a concept or an exact string?}
    
    Q2 -->|Declaration, signature, file, lines| S1["seek_symbol(symbol_name='...')"]
    Q2 -->|Callers who break on modification| S2["trace_symbol_impact(symbol='...', direction='upstream')"]
    Q2 -->|Dependencies this symbol relies on| S3["trace_symbol_impact(symbol='...', direction='downstream')"]
    
    Q3 -->|Conceptual behavior / feature logic| S4["search_knowledge_and_memory(prompt='...')"]
    Q3 -->|Literal non-AST token (error code, env var)| S5["Grep / literal search (Permitted Exception)"]
```

### When to Use Each Tool

| Goal | Primary Tool | Command Syntax |
|---|---|---|
| Jump to function, class, or method declaration | `seek_symbol` | `seek_symbol(symbol_name="TokenCounter")` |
| Disambiguate identical symbol across modules | `seek_symbol` | `seek_symbol(symbol_name="execute", file_hint="task_runner.py")` |
| Find all callers before refactoring / signature edit | `trace_symbol_impact` | `trace_symbol_impact(symbol="CausalSanitizer", direction="upstream", max_depth=3)` |
| Inspect downstream dependencies of a module | `trace_symbol_impact` | `trace_symbol_impact(symbol="ContextPacker", direction="downstream", max_depth=2)` |
| Conceptual or semantic discovery when name is unknown | `search_knowledge_and_memory` | `search_knowledge_and_memory(prompt="bi-temporal fact deduplication algorithm")` |
| Literal non-code string search (e.g., `"KORTEXT_ENV_VAR"`) | `run_command` (`grep`) | Permitted ONLY when searching non-AST literals. |

---

## Deterministic 3-Step Navigation Routine

When inspecting, modifying, or refactoring existing code, always follow this three-step pipeline:

```
┌────────────────────────────────────────────────────────┐
│ 1. SEEK: seek_symbol(symbol_name="Target")            │
│    → Returns file path, signature, exact line range   │
├────────────────────────────────────────────────────────┤
│ 2. IMPACT: trace_symbol_impact(symbol="Target")        │
│    → Maps affected upstream callers across codebase    │
├────────────────────────────────────────────────────────┤
│ 3. SURGICAL VIEW: view_file(AbsolutePath, Start, End)  │
│    → Read ONLY the target lines without token bleed   │
└────────────────────────────────────────────────────────┘
```

### Step 1: Seek Exact Declaration
```python
# Direct O(1) AST lookup in FalkorDB
result = seek_symbol(symbol_name="RetrievalEngine")
# Output provides: file, line_start, line_end, signature, docstring
```

### Step 2: Trace Blast Radius
```python
# Inspect all callers across the repository before touching code
impact = trace_symbol_impact(
    symbol="RetrievalEngine",
    direction="upstream",
    max_depth=2
)
# Output provides: affected_files, caller_signatures, total_references
```

### Step 3: Surgical Read
```python
# Read only the target declaration boundaries directly from disk
view_file(
    AbsolutePath=result["file"],
    StartLine=result["line_start"],
    EndLine=result["line_end"]
)
```

---

## Crisp Command Reference

### 1. `seek_symbol`
Deterministic symbol locator. Retrieves AST declaration, parameters, return type, and file location in $<2\text{ms}$.
```python
# Standard symbol lookup
seek_symbol(symbol_name="manage_tasks")

# Disambiguating overloaded or common symbol names
seek_symbol(symbol_name="dispatch", file_hint="dispatcher.py")
```

### 2. `trace_symbol_impact`
Multi-hop graph path traversal in FalkorDB over `REFERENCES`, `IMPORTS`, `CALLS`, and `IMPLEMENTS` edges.
```python
# Upstream impact: find callers who will break if symbol changes
trace_symbol_impact(
    symbol="InvariantGroundingEngine",
    direction="upstream",
    max_depth=3,
    token_budget=1500
)

# Downstream impact: find all internal dependencies of a symbol
trace_symbol_impact(
    symbol="InvariantGroundingEngine",
    direction="downstream",
    max_depth=2
)
```

### 3. `search_knowledge_and_memory`
5-Tier hybrid retrieval for conceptual and semantic queries when exact symbol names are unknown.
```python
# Semantic discovery of implementations and architectural patterns
search_knowledge_and_memory(
    prompt="How are FalkorDB Cypher parameters sanitized against injection?",
    collection="kortext_codebase"
)
```

---

## Anti-Patterns: FAIL vs PASS

### 1. Locating Symbol Declarations
```bash
# FAIL: Ripgrep loops scan hundreds of files, dumping noisy matches into context
rg "class TaskDispatcher" .
grep -rn "def process_symbol" src/
```
```python
# PASS: Instant O(1) AST resolution directly to file and exact line span
seek_symbol(symbol_name="TaskDispatcher")
seek_symbol(symbol_name="process_symbol")
```

### 2. Assessing Refactoring Blast Radius
```bash
# FAIL: Searching for symbol name as text finds comments, strings, and false hits
rg "record_system_outcome" .
```
```python
# PASS: Compiler-grade caller graph showing exact dependents and hops
trace_symbol_impact(symbol="record_system_outcome", direction="upstream", max_depth=3)
```

### 3. Codebase Exploration
```bash
# FAIL: Blindly reading whole files or guessing paths from directory listings
find src/ -name "*.py"
cat src/engine/retrieval.py
```
```python
# PASS: Semantic RAG retrieves relevant code chunks and architecture overviews
search_knowledge_and_memory(prompt="vector retrieval reranking pipeline")
```

---

## Verification & Compliance Checklist

Before concluding any code exploration or symbol modification:
- [ ] Symbol declaration was located via `seek_symbol` without filesystem text scans.
- [ ] Upstream callers were verified via `trace_symbol_impact(..., direction="upstream")`.
- [ ] File reads were confined to surgical line ranges (`view_file(StartLine=..., EndLine=...)`).
- [ ] Context token consumption remained under $<500$ tokens for the navigation step.
