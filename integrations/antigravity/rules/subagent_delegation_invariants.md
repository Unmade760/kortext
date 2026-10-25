---
trigger: model_decision
description: "Activate when planning complex multi-subsystem refactors (Complexity C >= 7) or orchestrating parallel subagent teams."
---

# Invariant [Subagent-Delegation-Protocol]

## Core Principle (Jose Parreño Garcia Agent Teams Alignment)

Single-agent execution with deterministic AST tools (`seek_symbol`, `trace_symbol_impact`) and disciplined context management is the **default** for routine engineering work (1–3 files, localized bug fixes, or Complexity Score $C < 7$). Because multi-agent handoffs incur a coordination and token tax, **do not** spawn subagents for routine 1–2 file edits.

Multi-agent Task DAG decomposition (`manage_tasks`) and subagent delegation (`invoke_subagent`) are warranted **only** when **Complexity Score $C \ge 7$** OR at least one of **Four Multi-Agent Triggers** is present:
1. **Context Saturation:** The task requires broad exploration or multi-module changes that would exceed a single context window.
2. **True Parallel Independence:** Multiple self-contained work units can execute concurrently on disjoint files/modules.
3. **Adversarial / Author-Reviewer Separation:** Security-critical changes requiring independent Red-Team (`kortext-security-auditor`) or QA (`kortext-code-reviewer`) verification.
4. **Specialized Persona Routing:** Work requiring distinct tool/permission boundaries (e.g., read-only research sweeps via `kortext-researcher`).

## Complexity Scoring Rubric ($C \in [0, 10]$)

Calculate the task complexity score $C$ prior to implementation:

| Dimension | Criteria | Points |
|---|---|---|
| **File Scope** | 1–2 files modified (e.g. implementation + unit test) | +0 |
| | 3–4 files touched or created | +1 |
| | 5+ files touched or created across packages | +3 |
| **Interface Surface** | Internal function, method, or localized fix | +0 |
| | Shared public API, MCP tool signature, or protocol change | +2 |
| | Database schema, graph schema, or storage migration | +3 |
| **System Layering** | Single module or subsystem | +0 |
| | Cross-layer (e.g., FastAPI route + FalkorDB + Qdrant) | +2 |
| **Risk & Blast Radius** | Additive feature or isolated bug fix (<5 callers) | +0 |
| | Core abstraction refactor (>10 upstream callers) | +2 |

- **If $C < 7$:** Execute directly inline using TDD (`seek_symbol` -> surgical edit -> `pytest`). Do not incur subagent spawning overhead.
- **If $C \ge 7$:** Initialize a Task DAG via `manage_tasks(action='create')` and delegate independent leaf tasks to subagents.

## Delegation Completion Contract & No Orphaned Subagents Rule

When decomposing work ($C \ge 7$) and dispatching child subagents, orchestrators must adhere to five invariants:

1. **No Orphaned Subagents (Your final message IS the deliverable).**
   Never end your turn with "waiting for background agents" — a spawned task is not a completed task. Wait for all delegated tasks to resolve, collect their 5-line report outcomes, and synthesize the composite deliverable before ending your turn.

2. **If you delegate, you own collection.**
   Fire-and-forget delegation is strictly forbidden. Inspect subagent evidence (`~/.kortext/handoffs/task_<id>_report.md`), confirm 100% test pass status, and verify AST invariants.

3. **Atomic Task Claiming (`action='claim'`).**
   When multiple workers poll the shared Task DAG, use `manage_tasks(action='claim', assigned_to='kortext-task-runner')` so FalkorDB atomically transitions a `ready` task to `in_progress`, records `base_commit`, and generates `.kortext/briefs/task_<id>_brief.md`.

4. **Worktree Isolation for Parallel Workers.**
   When running multiple `kortext-task-runner` subagents in parallel, isolate their workspaces using Git worktree branching (`Workspace: "branch"` in `invoke_subagent`) or ensure strictly disjoint file sets before running `pytest` so concurrent edits and test runs never collide.

5. **Compaction-Proof Progress Ledger (`.kortext/ledger.md`).**
   Maintain `.kortext/ledger.md` via `manage_tasks` so if parent context compacts at the 25% window ceiling, the orchestrator immediately recovers active goals, completed tasks, and architectural decisions.

## 5-Line Report File Contract (FM5)

Leaf workers write detailed logs to `~/.kortext/handoffs/task_<id>_report.md` and return only a 5-line summary via `send_message`:

```text
STATUS: PASS | FAIL | BLOCKED
COMMITS: <short_sha> (<files_changed_count> files)
TESTS: <passed>/<total> passing (<command>)
REPORT_PATH: ~/.kortext/handoffs/task_<id>_report.md
CONCERNS: none | <1-sentence blocker>
```

## 5-Round Fix Loop with Model Escalation

When subagent execution fails or tests reveal defects:
- **Rounds 1–2 (Targeted Self-Correction):** Inspect failure signatures and apply minimal surgical fixes.
- **Rounds 3–4 (Hypothesis Pivot):** Re-examine AST call hierarchies (`trace_symbol_impact`) and interface contracts.
- **Round 5 (Model Escalation & Circuit Breaker):** Escalate model tier or halt gracefully and report the exact diagnostic trace to the orchestrator.
