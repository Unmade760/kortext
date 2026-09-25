---
name: agentic-engineering
description: Multi-agent DAG task decomposition and subagent swarm routing patterns.
version: 1.0.0
triggers:
  - "orchestrate swarm"
  - "agentic decomposition"
---

# Agentic Engineering & Swarm Routing Protocol

## Directives:
1. When Complexity $C \ge 4$, decompose into Task DAG via `manage_tasks`.
2. Route leaf tasks to `cerebrum-task-runner` via `invoke_subagent`.
3. Consolidate results in parent context.
