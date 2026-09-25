---
name: task-orchestrator
description: Graph-backed Task DAG project management and subagent orchestration skill for Cerebrum. Activate whenever coordinating multi-step initiatives, managing dependencies between tasks, recovering from failed execution steps, or when the user invokes /orchestrate.
---

# Cerebrum Task DAG Orchestration Guide

## 1. Principles
- Any non-trivial multi-file task ($C \ge 4$) must be tracked in the FalkorDB Task DAG.
- Tasks transition through strictly validated states: `pending` -> `ready` -> `in_progress` -> `completed` / `failed` -> `blocked`.
- The `Stop` lifecycle hook blocks session completion if tasks remain pending or uncompleted without justification.

## 2. Managing the Task DAG
```python
# Create DAG
manage_tasks(
    action="create_dag",
    tasks=[
        {"task_id": "T1", "name": "Refactor RetrievalEngine", "depends_on": []},
        {"task_id": "T2", "name": "Verify Benchmarks", "depends_on": ["T1"]}
    ]
)

# Fetch unblocked tasks ready for execution
manage_tasks(action="get_ready")

# Transition task state
manage_tasks(action="update_status", task_id="T1", status="completed")
```

## 3. Subagent Dispatch
Dispatch each `ready` task to an isolated subagent (`cerebrum-task-runner`), passing the exact specification and dependencies. Collect only compact summaries (<300 tokens) back into the parent session context.
