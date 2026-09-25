---
name: cerebrum-architect
description: System architecture, refactoring, and blast-radius analysis runbook for Cerebrum. Activate whenever refactoring code, renaming or deleting symbols, restructuring codebases, analyzing blast radius, auditing architectural invariants, or running Louvain community clustering. Also activate when planning non-trivial changes or when the user invokes /cerebrum-architect.
---

# Cerebrum System Architecture & Refactoring Guide

## 1. When to Use
- Refactoring symbols, classes, methods, or modules.
- Measuring refactoring blast radius across the call graph before touching code.
- Restructuring directory hierarchies or breaking circular dependencies.
- Auditing architectural invariants across the AST.
- Executing graph maintenance, Louvain community clustering, or dream mode.

## 2. Invariant: Anti-Ripgrep First
Never run broad `ripgrep` or regex scans to understand architecture.
Always use deterministic symbol lookups:
```python
seek_symbol(symbol_name="TargetClass")
trace_symbol_impact(symbol_name="TargetClass", depth=3)
```

## 3. Two-Tier Complexity Gate
Before initiating non-trivial changes, evaluate complexity:
$$C(P) = \min(10, w_f \cdot F(P) + w_s \cdot S(P) + w_d \cdot D(P) + w_t \cdot T(P))$$
If $C \ge 4$:
1. Decompose the plan into a Task DAG using `manage_tasks(action="create_dag", ...)`.
2. Delegate execution to dedicated subagents (`cerebrum-task-runner`).
3. Commit verified outcomes using `record_system_outcome`.

## 4. Dream Mode Clustering & Maintenance
Run consolidation when modules drift:
```python
trigger_dream_mode(project="cerebrum", purge_stale=True)
```
