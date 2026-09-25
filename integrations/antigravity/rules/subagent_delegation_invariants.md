---
description: Mandatory rule requiring Task DAG decomposition and subagent delegation for multi-file modifications.
globs: ["**/*"]
always_apply: true
---

# Invariant [Subagent-Delegation-Mandate]

## Rule:
Whenever a proposed task touches 2 or more files, modifies a shared interface, or has a Complexity Score $C \ge 4$, the primary agent MUST NOT write code inline. The agent MUST:
1. Initialize a Task DAG via `manage_tasks(action='create')`.
2. Delegate leaf tasks to specialized subagents via `invoke_subagent`.
3. Preserve the primary context window for orchestration, verification, and user communication.

## Rationale:
Monolithic in-line execution exhausts parent context windows, causing hallucinations and regressions after 10 turns. Subagent isolation guarantees pristine execution environments and zero context bleed.
