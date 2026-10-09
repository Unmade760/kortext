---
trigger: always_on
description: "Mandatory rule requiring Task DAG decomposition and subagent delegation for multi-file modifications."
globs: "**/*"
---

# Invariant [Subagent-Delegation-Mandate]

## Core Rule
Whenever a proposed task touches **2 or more files**, modifies a **shared interface**, or has a **Complexity Score $C \ge 4$**, the primary agent MUST NOT write code inline.

The primary agent MUST:
1. Initialize an explicit Task DAG via `manage_tasks(action='create')`.
2. Decompose the objective into independent, isolated leaf tasks with explicit dependencies.
3. Delegate leaf task execution to specialized subagents (e.g., `kortext-task-runner`).
4. Preserve the primary context window strictly for orchestration, dependency tracking, verification, and user communication.

## Complexity Scoring Rubric ($C$)

Calculate the task complexity score $C$ prior to code implementation:

| Dimension | Criteria | Points |
|---|---|---|
| **File Scope** | Single file modification | +1 |
| | 2-3 files touched or created | +2 |
| | 4+ files touched or created | +3 |
| **Interface Surface** | Internal private function change | +0 |
| | Shared public API, interface, or protocol change | +2 |
| | Database schema, graph schema, or migration change | +2 |
| **System Layering** | Single layer (e.g., utility function only) | +0 |
| | Cross-layer (e.g., backend route + substrate + client) | +2 |
| **Risk & Impact** | Non-breaking additive feature | +0 |
| | Breaking change, refactoring core abstractions | +3 |

**Threshold Rule:** If total $C \ge 4$, inline code execution is strictly prohibited. You MUST build a Task DAG and delegate to subagents.

## The Task DAG Orchestration Protocol

```
           [Primary Orchestrator]
                     │
       manage_tasks(action='create')
                     │
         ┌───────────┴───────────┐
         ▼                       ▼
   [Leaf Task 1]           [Leaf Task 2]
         │                       │
         ▼                       ▼
  kortext-task-runner     kortext-task-runner
   (Pristine Context)      (Pristine Context)
         │                       │
         └───────────┬───────────┘
                     │
       send_message (Structured JSON)
                     │
                     ▼
           [Verification Gate]
```

### 1. Plan & Create DAG
- Call `manage_tasks(action='create')` defining:
  - `task_id`: Unique identifier (e.g., `task_01`)
  - `title`: Action-oriented description
  - `depends_on`: Dependencies establishing topological execution order
  - `acceptance_criteria`: Concrete test assertions or invariants

### 2. Delegate to Leaf Subagents
- Dispatch leaf tasks without unfulfilled dependencies to `kortext-task-runner`.
- Subagents receive only the context relevant to their task: symbol definitions (via `seek_symbol`), acceptance criteria, and target files.

### 3. Leaf Execution Discipline (TDD)
- Leaf subagents must follow strict TDD:
  1. RED: Write failing test first.
  2. GREEN: Implement minimal code to pass.
  3. REFACTOR: Clean structure and verify typing.
  4. VERIFY: 100% of test suite must pass (`uv run pytest`).

### 4. Structured Handoff Contract
Subagents must transmit a structured JSON payload upon completion:
```json
{
  "task_id": "task_xxxx",
  "status": "completed",
  "modified_files": [
    "/absolute/path/to/modified_file.py"
  ],
  "tests_passed": true,
  "test_summary": "145 passed, 1 warning in 3.32s",
  "evidence": "Verification description and test outcomes"
}
```

## Rationale & Cognitive Context Economics

1. **Context Exhaustion Prevention:** In-line editing across multiple files accumulates thousands of tokens of tool outputs, diffs, and compiler errors in the parent orchestrator context. By turn 10+, attention degradation causes dropped imports, forgotten instructions, and silent regressions.
2. **Context Isolation:** Subagent spawning isolates the implementation scratch space. Each subagent begins with a fresh context window dedicated entirely to making that specific task green.
3. **Parallelism:** Independent tasks in the DAG can be executed concurrently without state collisions.

