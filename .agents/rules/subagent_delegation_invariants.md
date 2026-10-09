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

## Delegation Completion Contract

When decomposing work and dispatching child subagents, orchestrators must adhere to three non-negotiable invariants:

1. **Your final message IS the deliverable.**
   Never end your turn with "waiting for background agents" — a spawned task is not a completed task. Ending your turn while children are running orphans their results (completed children cannot notify a parent whose turn has ended). Do not yield to the user until all delegated tasks have fully resolved, their outcomes are collected, and the composite deliverable is synthesized.

2. **If you delegate, you own collection.**
   Wait for results, integrate them, then return. Fire-and-forget delegation is strictly forbidden. The delegating orchestrator retains full accountability for inspecting subagent evidence, confirming 100% test pass status, checking AST invariants, and assembling final artifacts.

3. **Decompose only when work cannot fit in one context.**
   Do not re-delegate a task already sized for a single agent — depth is an outcome, not a plan. Subagent decomposition is a tool for context isolation and parallelism, not ritualistic bureaucracy. If a task fits comfortably within a single context window ($C < 4$, single file, bounded scope), execute it directly under strict TDD rather than spawning unnecessary subagent layers.

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
Leaf workers must never dump unformatted command outputs or raw diff logs into the parent context. Subagents must transmit a structured JSON payload upon completion via `send_message`:

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

#### Handoff Requirements:
- `task_id`: The exact identifier assigned in the Task DAG.
- `status`: `"completed"` if all acceptance criteria and tests pass; `"failed"` if blocked or unresolvable.
- `modified_files`: Complete array of absolute filesystem paths modified or created.
- `tests_passed`: Strict boolean indicating 100% pass rate. Must be `true` for `completed` status.
- `test_summary`: Quantitative test output (passed count, duration, failure count).
- `evidence`: Concrete verification evidence (test command executed, invariant verification, edge case validation).

## 5-Round Fix Loop with Model Escalation

When subagent execution fails or tests reveal defects, execution must follow a structured 5-round remediation loop with graduated escalation:

| Round | Strategy | Focus & Action |
|---|---|---|
| **Round 1-2** | **Targeted Self-Correction** | Inspect failure signatures, diffs, and compiler logs. Reproduce under isolated unit tests and apply minimal surgical fixes. Avoid broad refactoring. |
| **Round 3-4** | **Hypothesis Pivot** | Re-examine core assumptions, AST call hierarchies, and interface contracts. Check for substrate state issues or environmental drift. Isolate variables with focused reproduction tests. |
| **Round 5** | **Model Escalation & Circuit Breaker** | Escalate to higher reasoning model tier (e.g., fast tier -> frontier reasoning tier). If unresolved after Round 5, trigger circuit breaker: halt execution gracefully, preserve diagnostic logs, and report failure signature back to the orchestrator. |

### Remediation Rules:
- **Never Retry Blindly:** Never dispatch a retry with identical prompts. Every retry prompt must inject the exact error signature, failing assertion, and reproduction trace.
- **Preserve Baseline:** Revert exploratory changes that fail before trying alternate hypotheses to prevent compounding errors.
- **Escalate Model Tier:** When lower-tier models hit reasoning walls in complex logic, route subsequent attempts to higher-tier reasoning models.

## Multi-Perspective Split-Role Analysis

For complex architectural tasks ($C \ge 6$), multi-system refactorings, or ambiguous problem domains, the orchestrator or subagent must evaluate proposals across four distinct analytical perspectives before committing code:

1. **Factual Reviewer**
   - **Mandate:** Ground truth verification and empirical audit.
   - **Checks:** Verifies all claims, file paths, symbol declarations, and schema structures against the primary codebase via `seek_symbol`. Rejects speculative assertions, hallucinated APIs, or undocumented dependencies.

2. **System Architect**
   - **Mandate:** Structural cohesion, boundary integrity, and system lifecycle.
   - **Checks:** Evaluates modularity, dependency direction, coupling, cross-layer boundaries, and blast radius via `trace_symbol_impact`. Ensures alignment with the Sole Custodian model and IPC socket transports.

3. **Security Auditor**
   - **Mandate:** Threat mitigation, isolation, and defensive invariants.
   - **Checks:** Enforces zero hardcoded secrets, strict input validation schemas, parameterized Cypher/SQL queries, command injection defense, and MINJA causal memory sanitization with trust level anchoring (`system` vs `verified` vs `untrusted`).

4. **Invariant Enforcer**
   - **Mandate:** System policies and operational consistency.
   - **Checks:** Guarantees adherence to mandatory rules: AST deterministic lookup over ripgrep, FastMCP Sole Custodian access for vector stores, Task DAG decomposition for $C \ge 4$, immutability patterns, and 100% test pass verification under TDD.

## Rationale & Cognitive Context Economics

1. **Context Exhaustion Prevention:** In-line editing across multiple files accumulates thousands of tokens of tool outputs, diffs, and compiler errors in the parent orchestrator context. By turn 10+, attention degradation causes dropped imports, forgotten instructions, and silent regressions.
2. **Context Isolation:** Subagent spawning isolates the implementation scratch space. Each subagent begins with a fresh context window dedicated entirely to making that specific task green.
3. **Parallelism:** Independent tasks in the DAG can be executed concurrently without state collisions.

