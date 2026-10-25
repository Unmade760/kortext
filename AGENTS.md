# Kortext Antigravity System - Agent Instructions (v2.0.0)

Production-ready cognitive substrate providing AST-indexed symbol navigation, 4-tier hybrid memory, and artifact-first handoffs for software engineering.

## Core Principles

1. **Deterministic Navigation** - Never use brute-force `ripgrep`/`rg` for code symbols; navigate via compiler-grade AST indices.
2. **Test-Driven Discipline (TDD)** - Write failing tests first (RED -> GREEN -> REFACTOR), maintaining 80%+ coverage (`uv run pytest -q`).
3. **Security & Immutability** - Validate boundary inputs, never hardcode secrets, enforce MINJA causal sanitization, and prefer immutable data structures (`frozen=True`).
4. **Right-Sized Delegation** - Do not spawn subagents for routine 1–3 file edits. Delegate only when task complexity $C \ge 7$ or touches $\ge 4$ independent modules.

## Kortext System Invariants

### Invariant 1: Anti-Ripgrep Mandate
Never execute `ripgrep`, `rg`, or broad `grep_search` scans to locate code declarations, signatures, or call sites:
- **Locate symbol declaration & call hierarchy:** `seek_symbol(symbol_name="<symbol>")` (<2ms).
- **Assess multi-hop blast radius:** `trace_symbol_impact(symbol="<symbol>", direction="upstream"|"downstream")`.
- **Conceptual & episodic retrieval:** `search_knowledge_and_memory(query="<intent>")`.

### Invariant 2: Subagent Delegation & Artifact-First Handoffs
When complexity $C \ge 7$ or $\ge 4$ independent modules are modified:
1. Track tasks via `manage_tasks` or unified handoff batons (`memory_session_handoff`).
2. Subagents write detailed findings/diffs to `~/.kortext/handoffs/<task_id>.json` and return a $<150$-token summary:
```json
{
  "baton_id": "task_xxxx",
  "task_id": "task_xxxx",
  "status": "completed",
  "handoff_ref": "handoff:task_xxxx",
  "artifact_path": "~/.kortext/handoffs/task_xxxx.json",
  "modified_files": ["/absolute/path/to/file.py"],
  "test_command": "pytest tests/test_target.py -q",
  "tests_passed": true,
  "test_summary": "145 passed in 3.32s",
  "summary": "Concise <150-token summary of verified outcome",
  "evidence": "Verification description and test outcomes"
}
```

### Invariant 3: Substrate Resilience Mandate
1. Connect to FalkorDB via Unix Domain Socket (`~/.kortext/run/falkordb.sock`) with loopback TCP (`127.0.0.1:6379`) fallback.
2. Route vector operations through the FastMCP Sole Custodian (`kortext.server`) or `managed_qdrant_client`; never open concurrent `QdrantClient(path=...)` locks on `~/.kortext/qdrant`.

## Available Subagents

| Agent | Purpose | When to Use |
| :--- | :--- | :--- |
| **`kortext-architect`** | System design, blast-radius analysis, refactoring plans | Multi-module refactoring ($C \ge 7$ or $\ge 4$ files) |
| **`kortext-task-runner`** | Leaf-node TDD execution worker | Isolated leaf tasks, surgical bug fixes |
| **`kortext-code-reviewer`** | Invariant, security, and AST drift review | After code modifications, before commits |
| **`kortext-researcher`** | Deep 4-tier memory search and AST path tracing | Unfamiliar subsystems, cross-repo exploration |

## Project Structure

- `kortext/` - Core cognitive substrate, dual-memory engines, AST chunkers, hooks, and FastMCP server
- `integrations/antigravity/` - Canonical plugin source (`agents/`, `skills/`, `rules/`, `sidecars/`, `daemons/`, `hooks.json`)
- `scripts/` - Plugin installer and substrate lifecycle scripts
- `tests/` - Pytest unit, integration, and benchmark suite
