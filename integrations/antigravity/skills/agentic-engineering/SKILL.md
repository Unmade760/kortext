---
name: agentic-engineering
description: Operate as an agentic engineer using eval-first execution, task decomposition, model routing, cost discipline, Task DAG orchestration via manage_tasks, and deterministic symbol navigation via seek_symbol.
version: 2.0.0
triggers:
  - "agentic engineering"
  - "eval-first loop"
  - "15-minute rule"
  - "model routing"
  - "task dag"
  - "orchestrate swarm"
metadata:
  origin: ECC
  adapted_for: Kortext
---

# Agentic Engineering

Use this skill for engineering workflows where AI agents perform implementation work and humans/orchestrators enforce quality, risk controls, and architectural invariants.

---

## Operating Principles

1. **Completion Criteria First:** Define executable verification checks and capability evals before execution begins.
2. **Decompose into Agent-Sized Units:** Apply the 15-minute unit rule to isolate risk and avoid context blowout.
3. **Route Model Tiers by Task Complexity:** Match reasoning depth to problem hardness.
4. **Measure with Evals and Regression Checks:** Rely on deterministic test suites, not visual inspection.
5. **Deterministic Symbol Seeking:** Locate symbols via AST indices (`seek_symbol`) instead of brute-force regex scanning.
6. **Subagent Workspace Isolation:** Dispatch complex multi-file tasks ($C \ge 4$) to leaf subagents to protect parent context economics.

---

## Eval-First Loop

Before editing code:

1. **Define Capability & Regression Evals:** Identify the target behavior to verify and existing test suites to protect against regression.
2. **Run Baseline & Capture Failure Signatures:** Confirm the expected test failure (RED state).
3. **Execute Implementation:** Perform surgical edits guided by test assertions.
4. **Re-Run Evals & Compare Deltas:** Confirm GREEN pass rate with zero unexpected regressions.

---

## Task Decomposition (The 15-Minute Unit Rule)

Deconstruct complex epics into atomic work units:
- **Independently Verifiable:** Each unit must have an executable validation command (`pytest`, `npm test`).
- **Single Dominant Risk:** Each unit addresses one concern (schema, repository, API route, or test suite).
- **Clear Done Condition:** State exactly what files change and what evidence proves completion.

---

## Model Routing

Optimize latency, cost, and reasoning depth:

- **Haiku / Flash (Fast Tier):** Classification, boilerplate transforms, single-function edits, test runner wrappers.
- **Sonnet / Pro (Balanced Tier):** Feature implementation, refactoring, unit and integration test authoring.
- **Opus / Ultra (High-Reasoning Tier):** Architecture design, complex multi-file invariants, root-cause debugging, security audits.

**Rule:** Escalate model tier only when a lower tier fails with an identifiable reasoning gap.

---

## Task DAG Orchestration via `manage_tasks`

When tasks form dependencies or require multi-session tracking, manage them in FalkorDB using the `manage_tasks` tool:

```python
# 1. Create atomic tasks in the DAG
manage_tasks(
    action="create",
    task_id="task_schema_01",
    title="Implement UserSession Schema",
    description="Add UserSession Pydantic model with TTL validation",
    dependencies=[]
)

manage_tasks(
    action="create",
    task_id="task_service_02",
    title="Implement SessionService Repository",
    description="Connect UserSession to storage with exponential backoff",
    dependencies=["task_schema_01"]
)

# 2. Query unblocked ready tasks
ready = manage_tasks(action="get_ready")

# 3. Mark task completed upon verified test pass
manage_tasks(
    action="update_status",
    task_id="task_schema_01",
    status="completed"
)
```

### DAG Invariants:
- **Strict Acyclicity:** Dependencies must form a directed acyclic graph.
- **Explicit Ingress/Egress:** Every task records inputs, target files, and verification commands.

---

## Deterministic Code Navigation via `seek_symbol`

Do not waste context tokens grep-searching directories (`rg`, `grep -r`). In Kortext, locate symbols deterministically via Tree-sitter AST and SCIP indexes:

```python
# Jump straight to symbol declaration and line range
seek_symbol(symbol_name="SessionService")

# Trace call graph impact before refactoring
trace_symbol_impact(symbol_name="SessionService", depth=2)
```

---

## Subagent Workspace & Context Isolation ($C \ge 4$)

Whenever a task touches multiple files, alters core architecture, or requires iterative debugging:
- **Parent / Orchestrator:** Maintains DAG state, dispatches work, monitors progress, and synthesizes outcomes.
- **Leaf Subagent (`kortext-task-runner`):** Executes in an isolated context window, performs surgical edits via `replace_file_content`, verifies tests, and returns a concise structured handoff (<300 tokens).

### Structured Verification Handoff Format:
```json
{
  "task_id": "task_schema_01",
  "status": "completed",
  "modified_files": [
    "src/schemas/session.py",
    "tests/test_session.py"
  ],
  "verification": {
    "test_command": "pytest tests/test_session.py",
    "passed": 6,
    "failed": 0,
    "exit_code": 0
  },
  "summary": "Implemented UserSession model with TTL validation and 100% test pass rate."
}
```

---

## Session Strategy

- **Continue Session:** For closely-coupled units sharing immediate working context.
- **Start Fresh Session:** After major phase transitions (e.g., from Planning to Execution, or after merging a major milestone).
- **Compact Strategically:** Proactively compact context at milestone boundaries, not mid-debug.

---

## Review Focus for AI-Generated Code

Prioritize:
- Invariants and boundary conditions
- Error handling and recovery paths
- Security, auth, and input sanitization
- Hidden coupling and state drift

Do not waste review cycles on formatting or style disagreements when automated formatters (`ruff`, `prettier`) and typecheckers enforce standards.

---

## Cost Discipline

Track per task:
- Model tier
- Token estimate
- Retries count
- Wall-clock execution time
- Success / failure outcome

On initiative completion, persist learnings to episodic memory via `record_system_outcome`.
