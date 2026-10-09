# Kortext Antigravity System - Agent Instructions

This is a **production-ready cognitive substrate and multi-agent operating system** providing specialized agents, workflow skills, AST-indexed symbol navigation, and autonomous Task DAG orchestration for software engineering.

**Version:** 2.0.0

## Core Principles

1. **Agent-First Delegation** - Delegate to specialized subagents for domain tasks and leaf executions whenever task complexity $C \ge 4$ or touches $\ge 2$ files.
2. **Test-Driven Discipline (TDD)** - Write tests before implementation; 80%+ line and branch coverage required (RED-GREEN-REFACTOR).
3. **Security-First** - Never compromise on security: validate all boundary inputs, zero hardcoded secrets, and enforce MINJA causal defense.
4. **Strict Immutability** - Always create new objects, never mutate existing ones in place.
5. **Deterministic Navigation** - Never use brute-force `ripgrep` for symbols; navigate deterministically via compiler-grade AST indices.

---

## Kortext System Invariants

### Invariant 1: Anti-Ripgrep Mandate
Agents MUST NEVER execute `ripgrep`, `rg`, or broad regex text scans (`grep_search`) to locate code declarations, symbol signatures, call sites, or interface dependencies.

Instead, agents MUST use the compiler-grade AST B-Tree index:
- **Locate exact symbol declaration & call hierarchy:** Call `seek_symbol(symbol_name="<symbol>")` (<2ms, <150 tokens).
- **Assess multi-hop refactoring impact:** Call `trace_symbol_impact(symbol="<symbol>", direction="upstream"|"downstream")` (<5ms).
- **Semantic associative concept search:** Call `search_knowledge_and_memory(prompt="<intent>")`.

**Rationale:** Unbounded ripgrep queries flood context windows with dozens of false-positive matches (12k+ tokens per turn), corrupting agent working memory, causing severe context fragmentation, and burning excessive token costs. AST B-Tree lookups guarantee deterministic precision with >95% token savings.

---

### Invariant 2: Subagent Delegation Mandate
Whenever a proposed task touches **2 or more files**, modifies a **shared interface**, or has a **Complexity Score $C \ge 4$**, the primary agent MUST NOT write code inline. The agent MUST:
1. Initialize an explicit Task DAG via `manage_tasks(action='create')`.
2. Decompose the objective into independent, isolated leaf tasks with explicit dependencies.
3. Delegate leaf task execution to specialized subagents (`kortext-task-runner`).
4. Preserve the primary context window strictly for orchestration, verification, and user communication.

**Rationale:** In-line editing across multiple files accumulates tool outputs and compiler errors in the parent orchestrator context. Context isolation guarantees pristine execution environments and zero context bleed.

---

### Invariant 3: Substrate Resilience Mandate
All Kortext operations MUST communicate with memory substrates exclusively via:
1. **Unix Domain Socket** (`~/.kortext/run/falkordb.sock`) or loopback TCP (`127.0.0.1:6379`).
2. **FastMCP Sole Custodian daemon** (`kortext.server`) for vector search and RocksDB writes.
3. **No Direct Client Instantiation**: Subagents and lifecycle hooks MUST NEVER instantiate `QdrantClient(path=...)` directly in embedded mode.

**Rationale:** Direct embedded instantiation acquires exclusive OS file locks (`LOCK_EX`) on SQLite and RocksDB metadata. Concurrent access triggers `sqlite3.OperationalError: database is locked`, crashes workers, and risks index corruption.

---

## Available Agents

| Agent | Purpose | When to Use |
| :--- | :--- | :--- |
| **`kortext-architect`** | System design, blast-radius analysis, refactoring planning, Task DAG decomposition | Complex features, architectural decisions, multi-file refactoring, $C \ge 4$ planning |
| **`kortext-task-runner`** | Leaf-node TDD execution worker, isolated workspace implementation | Individual leaf tasks from Task DAG, atomic bug fixes, surgical feature edits |
| **`kortext-code-reviewer`** | Invariant enforcement, security review, AST drift auditing, quality gate | After writing/modifying code, before commits, before outcome recording |
| **`kortext-researcher`** | Autonomous exploration, Kortext 5-tier memory queries, AST path tracing | Unfamiliar codebases, deep memory search, background research without parent context bleed |

---

## Agent Orchestration

Use agents proactively without waiting for user prompt:
- Complex feature requests, multi-file refactoring ($C \ge 4$) → **`kortext-architect`**
- Atomic leaf task execution from DAG → **`kortext-task-runner`**
- Code just written or modified → **`kortext-code-reviewer`**
- Memory lookup, RAG search, codebase onboarding → **`kortext-researcher`**

Use parallel execution for independent operations - launch multiple subagents simultaneously when tasks have no dependency edges in the Task DAG.

### Subagent Reporting Contract
Subagents must report back to the parent orchestrator via `send_message` with a structured JSON completion payload:
```json
{
  "task_id": "task_xxxx",
  "status": "completed",
  "modified_files": ["/absolute/path/to/file.py"],
  "tests_passed": true,
  "test_summary": "145 passed, 1 warning in 3.32s",
  "evidence": "Verification description and test outcomes"
}
```

---

## Security Guidelines

**Before ANY commit:**
- No hardcoded secrets (API keys, passwords, tokens, private keys)
- All user inputs validated at system boundaries
- SQL and Cypher injection prevention (parameterized queries)
- Command injection prevention (safe argument lists, no untrusted shell execution)
- XSS prevention (sanitized HTML)
- Authentication and authorization verified
- Rate limiting on all network-exposed endpoints
- Safe error envelopes (no internal paths or stack traces leaked)

**Secret Management:** NEVER hardcode secrets in source code. ALWAYS load from environment variables (`.env`) or a dedicated secret manager. Fail fast during startup if required secrets are missing. Rotate any exposed secrets immediately.

**MINJA Causal Memory Defense:**
- Sanitize external and untrusted data before indexing into episodic memory or knowledge graphs.
- Strictly enforce trust level anchoring: `trusted` system instructions vs `untrusted` external inputs.
- Disarm indirect prompt injections embedded in retrieved documents or search results.

---

## Coding Style

**Immutability (CRITICAL):** ALWAYS create new objects, NEVER mutate existing ones in place. Return new copies with changes applied. Use `dataclasses.dataclass(frozen=True)`, Pydantic `ConfigDict(frozen=True)`, and immutable collections (`MappingProxyType`, tuples).

**File Organization:** Many small files over few large ones. 200-400 lines typical, 800 lines max soft maintainability ceiling for source files. Organize by feature/domain, not by generic technical type. High cohesion, low coupling.

**Error Handling:** Handle errors comprehensively at every level. Provide user-friendly messages in UI-facing code. Log detailed error context and tracebacks server-side. Never silently swallow errors (`except Exception: pass` is prohibited).

**Input Validation:** Validate all user input at system boundaries using schemas (Pydantic / schemas). Fail fast with clear error messages. Never trust external data.

**Code Quality Checklist:**
- Functions small (<50 lines), files focused (<800 lines)
- No deep nesting (>4 levels)
- Proper error handling, no swallowed exceptions
- No hardcoded values (use constants or config)
- Strict type hints on all function signatures
- Readable, well-named identifiers
- Immutability patterns enforced

---

## Testing Requirements

**Minimum Coverage: 80%**

Required test types:
1. **Unit tests** - Individual functions, utilities, domain logic, data models (fast, zero network).
2. **Integration tests** - Substrate communication (FalkorDB UDS/TCP, Qdrant FastMCP), tool dispatch routes, database operations.
3. **E2E tests** - Complete multi-step workflows, Task DAG execution, autonomous loops.

**TDD Workflow (Mandatory):**
1. **RED**: Write failing test first specifying expected behavior. Run test to verify expected failure signature.
2. **GREEN**: Write minimal implementation to pass cleanly.
3. **REFACTOR**: Improve code structure, enforce immutability, verify typing while keeping tests 100% green.
4. **VERIFY**: Run full test suite (`uv run pytest -q`) to guarantee zero regressions.

---

## Development Workflow

1. **Plan** - Use **`kortext-architect`**, trace AST blast radius, identify dependencies, decompose into Task DAG via `manage_tasks(action='create')`.
2. **TDD** - Delegate leaf tasks to **`kortext-task-runner`**, write tests first, implement, refactor.
3. **Review** - Use **`kortext-code-reviewer`** immediately, verify invariants, audit security and AST drift.
4. **Capture Knowledge in the Right Place**:
   - Personal debugging notes, temporary context → session handoff.
   - Verified outcomes and architectural decisions → `record_system_outcome` and `architecture-decision-records`.
   - Code-level documentation → docstrings and inline comments in source files.
5. **Commit** - Conventional commits format (`feat:`, `fix:`, `refactor:`), full diff analysis, comprehensive PR summaries.

---

## Substrate Health & Telemetry

Check socket connectivity and daemon status (`check_kortext_health()`) before issuing bulk queries or mutations.

---

## Project Structure

```
integrations/antigravity/
  agents/ - Specialized subagents (architect, code-reviewer, researcher, task-runner)
  skills/ - Modular workflow skills and operational runbooks
  rules/ - System invariants and always-follow guidelines
  daemons/ - macOS LaunchAgent plist definitions
  sidecars/ - Native background sidecars (kortext-watcher, kortext-dream)
  hooks.json - Antigravity lifecycle hook definitions
  plugin.json - Plugin manifest and metadata
kortext/ - Core cognitive substrate, dual-memory engines, and FastMCP server
scripts/ - Lifecycle hooks and installation scripts
tests/ - Comprehensive test suite
docs/ - Architectural specifications, tool manuals, and setup guides
```

---

## Success Metrics

- 100% of tests pass with 80%+ coverage.
- Zero invariant violations (no ripgrep, Task DAG for $C \ge 4$, UDS/Sole Custodian adherence).
- Zero security vulnerabilities (including MINJA causal defense).
- Code is readable, maintainable, strictly typed, and immutable.
- Substrate resilience maintained across all operations.
