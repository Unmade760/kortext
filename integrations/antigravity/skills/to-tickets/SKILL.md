---
name: to-tickets
description: Use when slicing specifications or plans into vertical tracer-bullet tasks, charting large initiatives across the Frontier and Fog of War (wayfinder), or registering a dependency Task DAG in FalkorDB via manage_tasks.
---

# To-Tickets: Vertical Tracer-Bullet Slicing & Wayfinder DAG Charting

Converts engineering specifications and large initiatives into atomic, vertical tracer-bullet tickets registered as an acyclic Task DAG in FalkorDB (`manage_tasks`).

## 1. Wayfinder Initiative Charting: Destination, Frontier & Fog of War

Never generate speculative implementation tickets deep inside unexplored architecture. Partition every initiative into three zones:

| Zone | Definition | Operational Rule |
|---|---|---|
| **Destination (North Star)** | Measurable end-state goal and non-negotiable architectural invariants | Fixed unless amended by an explicit ADR (`to-spec`). |
| **Frontier (Active Boundary)** | Unblocked tickets where dependencies and interfaces are known (`get_ready`) | Dispatch agents **strictly along the Frontier**; resolve uncertainty tickets first. |
| **Fog of War (Unexplored)** | Downstream zones with unvalidated APIs, unknown latencies, or unresolved trade-offs | Do **not** write production code here; deploy `Research`, `Prototype`, or `Grilling` tickets first. |

### The 4 Ticket Archetypes

| Archetype | Autonomy Mode | Assigned Role | Purpose & Exit Artifact |
|---|---|---|---|
| **`Research`** | Autonomous (AFK) | `kortext-researcher` | Answer technical/library/benchmark questions $\rightarrow$ `<150`-token brief + `~/.kortext/handoffs/<id>.json` |
| **`Grilling`** | Interactive (HITL) | Orchestrator + Human | Resolve 3–5 architectural forks using concrete Option A/B recommendations $\rightarrow$ signed-off spec/ADR |
| **`Prototype`** | Rapid Tracer Spike | `kortext-task-runner` | Validate feasibility on a disposable branch $\rightarrow$ benchmark metric or verified contract |
| **`Task`** | Atomic SWE (TDD) | `kortext-task-runner` | Production code slice (`<300` lines diff, `1–3` files) $\rightarrow$ 100% passing tests + `handoff:<id>` |

## 2. Vertical Tracer Bullets vs. Horizontal Layer Slicing

Always slice `Task` tickets **vertically** through the stack (`Schema -> Domain Logic -> API/Tool -> Tests`) rather than horizontally (`all schemas` then `all services` then `all tests`).

| Slicing Style | Structure | Why It Succeeds or Fails |
|---|---|---|
| **Horizontal (REJECT)** | Ticket 1: All models; Ticket 2: All repos; Ticket 3: All tests | Defers integration feedback; causes mock drift and massive merge collisions. |
| **Vertical Tracer (MANDATORY)** | Tracer 1: End-to-end minimal happy path + test; Tracer 2: Edge cases + cache + test | Every completed ticket is independently runnable, testable, and shippable. |

### Context Window Budgeting Rules (The 15-Minute Unit Rule)
1. **Diff Ceiling**: `<300` lines of code changed (including unit tests).
2. **File Limit**: `1–3` tightly cohesive files per ticket (`model.py`, `service.py`, `test_service.py`).
3. **Disjoint Ownership**: Parallel sibling tickets must have zero overlapping `target_files` (verified via `detect_file_overlaps`). If two tickets share 1-hop AST callers/callees, either sequence them via `depends_on` or require `recommended_workspace_mode="branch"`.

## 3. Programmatic DAG Registration via `manage_tasks`

Ground target symbols with `seek_symbol` first, then register the DAG in FalkorDB:

```python
manage_tasks(
    action="create",
    tasks=[
        {
            "id": "TASK_001_TRACER",
            "title": "Implement SessionCheckpoint Model & Repository Tracer",
            "archetype": "Task",
            "description": "Add frozen SessionCheckpoint model and parameterized FalkorDB upsert with unit tests.",
            "target_files": ["kortext/models/checkpoint.py", "tests/test_checkpoint.py"],
            "depends_on": [],
            "test_command": "uv run pytest tests/test_checkpoint.py -q",
        },
        {
            "id": "TASK_002_MCP_TOOL",
            "title": "Expose checkpoint_session via FastMCP",
            "archetype": "Task",
            "description": "Register checkpoint_session tool calling SessionCheckpoint repository.",
            "target_files": ["kortext/server.py", "tests/test_server_checkpoint.py"],
            "depends_on": ["TASK_001_TRACER"],
            "test_command": "uv run pytest tests/test_server_checkpoint.py -q",
        },
    ],
)
```

## 4. Non-Negotiable Definition of Done (DoD) per Ticket

Every ticket brief must enforce these 5 completion gates:
- [ ] **Strict TDD**: Failing test verified (RED) before production edit; minimal fix passes (GREEN); cleaned up (REFACTOR).
- [ ] **Scope & File Confinement**: Diff `<300` lines; only declared `target_files` modified; zero `unittest.mock` in production files.
- [ ] **AST & Security Invariants**: `seek_symbol` / `trace_symbol_impact` used (no `rg` sweeps); parameterized Cypher/SQL (`$param`); frozen models.
- [ ] **Fresh Test Execution**: Ticket `test_command` and `uv run pytest -q` pass with exit code `0` in the current turn.
- [ ] **Artifact-First Handoff**: Completed via `manage_tasks(action="complete_task", ...)` emitting `~/.kortext/handoffs/<task_id>.json` (`<150`-token summary).
