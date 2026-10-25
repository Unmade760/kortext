---
name: kortext-boost
description: Use when tackling tricky concurrency bugs, race conditions, algorithmic optimizations, or multi-file refactors requiring AST pre-grounding, isolated subagent execution, and independent verification (/boost adaptation).
---

# Kortext Boost: 3-Phase AST-Grounded Deep Reasoning (`/kortext-boost`)

Adapts Antigravity's `/boost` 3-phase reasoning hierarchy (`Orchestrator` $\rightarrow$ `DeepInvestigator` / `DeepCoder` $\rightarrow$ `Synthesis & Verification`) with deterministic Kortext Tier-0 AST pre-grounding (`<15ms`) and artifact-first handoffs.

## Phase 1: Deterministic AST Grounding & Strategy Formulation (`<15ms`)

1. **Generate the Grounded Execution Brief**:
   Call `boost_prompt_context(prompt="<user objective>")` (or `seek_symbol` + `trace_symbol_impact`) immediately on Turn 0:
   ```python
   brief = boost_prompt_context(prompt="Fix race condition in session cache and add unit tests")
   ```
2. **Inspect Blast Radius & Active Invariants**:
   - Review `target_symbols`, `file_skeletons`, `blast_radius_callers`, `active_invariants`, and `execution_routing` returned by `boost_prompt_context`.
   - Never run broad `rg` or `grep_search` sweeps when `target_symbols` are resolved.
3. **Select Execution Topology**:
   - **Single-File / Low Coupling ($C < 7$)**: Execute inline using strict RED-GREEN-REFACTOR TDD.
   - **Multi-File / Coupled Subsystems ($C \ge 7$)**: Register atomic vertical slices via `manage_tasks(action="create", tasks=[...])` and verify disjoint file ownership via `detect_file_overlaps`.

## Phase 2: Isolated Parallel Execution & Red-Team Investigation

Dispatch focused subagents with clean context windows and explicit file boundaries:

1. **Deep Investigation Stream (`kortext-researcher`, `model: flash`, read-only)**:
   - Trace upstream/downstream call chains via `trace_symbol_impact` and verify root-cause hypotheses without mutating files.
2. **Deep Coding Stream (`kortext-task-runner`, `Workspace: branch` when coupled)**:
   - Claim ready task via `manage_tasks(action="claim")`.
   - Write failing reproduction test first (RED) $\rightarrow$ implement minimal immutable fix within `target_files` (GREEN) $\rightarrow$ run local verification command (`uv run pytest -q`).
3. **Red-Team Challenge (`kortext-code-reviewer`)**:
   - Challenge assumptions, check all 1-hop and 2-hop upstream callers from `trace_symbol_impact`, and verify zero silent `except Exception: pass` fallbacks.

## Phase 3: Synthesis, Ground-Truth Verification & Persistence

1. **Full Regression & Invariant Check**:
   - Execute the workspace verification command (`uv run pytest -q`) in the current turn so `PostToolUse` records a fresh passing proof in `~/.kortext/run/last_test_run.json`.
   - If modifying grounded symbols, verify `check_kortext_health()` reports `0` drifted invariants.
2. **Artifact-First Completion**:
   - Complete active DAG nodes via `manage_tasks(action="complete_task", ...)` and record architectural decisions or bug root causes via `record_system_outcome(category="bugfix" | "refactor", trust_level="tool_confirmed")`.
