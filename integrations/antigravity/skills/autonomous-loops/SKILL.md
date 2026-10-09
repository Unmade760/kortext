---
name: autonomous-loops
description: Patterns and architectures for autonomous execution loops - from simple sequential pipelines to RFC-driven multi-agent DAG systems, Antigravity background sidecars, and Cognitive Dream Mode execution.
version: 2.0.0
triggers:
  - "autonomous loop"
  - "background sidecar"
  - "continuous agent loop"
  - "ralphinho dag"
  - "de-sloppify"
metadata:
  origin: ECC
  adapted_for: Kortext
---

# Autonomous Loops Skill

Patterns, architectures, and reference implementations for running agent workflows autonomously in loops. Covers everything from simple non-interactive pipelines to full RFC-driven multi-agent DAG orchestration, background sidecars, and Kortext Cognitive Dream Mode.

## When to Use

- Setting up autonomous development workflows that run without human intervention
- Choosing the right loop architecture for your problem (simple vs complex)
- Building CI/CD-style continuous development pipelines
- Running parallel agents with merge coordination
- Implementing context persistence across loop iterations
- Adding quality gates and cleanup passes to autonomous workflows
- Running background cron sidecars, watchers, and memory consolidation loops

## Loop Pattern Spectrum

From simplest to most sophisticated:

| Pattern | Complexity | Best For |
|---------|-----------|----------|
| [Sequential Pipeline](#1-sequential-pipeline-non-interactive) | Low | Daily dev steps, scripted workflows |
| [NanoClaw / Persistent REPL](#2-nanoclaw--persistent-repl) | Low | Interactive persistent sessions |
| [Infinite Agentic Loop](#3-infinite-agentic-loop) | Medium | Parallel content generation, spec-driven work |
| [Continuous PR Loop](#4-continuous-pr-loop) | Medium | Multi-day iterative projects with CI gates |
| [De-Sloppify Pattern](#5-the-de-sloppify-pattern) | Add-on | Quality cleanup after any Implementer step |
| [Ralphinho / RFC-Driven DAG](#6-ralphinho--rfc-driven-dag-orchestration) | High | Large features, multi-unit parallel work with merge queue |
| [Antigravity Sidecars & Dream Loops](#7-antigravity-background-hooks--cognitive-dream-mode) | Substrate | Background memory consolidation, file watching, proactive sleep sweeps |

---

## 1. Sequential Pipeline (Non-Interactive)

**The simplest loop.** Break daily development into a sequence of non-interactive agent calls. Each call is a focused step with a clear prompt.

### Core Insight

> If you can't figure out a loop like this, it means you can't even drive the LLM to fix your code in interactive mode.

Run non-interactive agent commands with a focused prompt, exiting when done. Chain calls to build a pipeline:

```bash
#!/bin/bash
# daily-dev.sh - Sequential pipeline for a feature branch

set -e

# Step 1: Implement the feature
agent-cli -p "Read the spec in docs/auth-spec.md. Implement OAuth2 login in src/auth/. Write tests first (TDD). Do NOT create any new documentation files."

# Step 2: De-sloppify (cleanup pass)
agent-cli -p "Review all files changed by the previous commit. Remove any unnecessary type tests, overly defensive checks, or testing of language features (e.g., testing that TypeScript generics work). Keep real business logic tests. Run the test suite after cleanup."

# Step 3: Verify
agent-cli -p "Run the full build, lint, type check, and test suite. Fix any failures. Do not add new features."

# Step 4: Commit
agent-cli -p "Create a conventional commit for all staged changes. Use 'feat: add OAuth2 login flow' as the message."
```

### Key Design Principles

1. **Each step is isolated** - A fresh context window per call means no context bleed between steps.
2. **Order matters** - Steps execute sequentially. Each builds on the filesystem state left by the previous.
3. **Negative instructions are dangerous** - Don't say "don't test type systems." Instead, add a separate cleanup step (see [De-Sloppify Pattern](#5-the-de-sloppify-pattern)).
4. **Exit codes propagate** - `set -e` stops the pipeline on failure.

### Variations

**With model routing:**
```bash
# Research with Opus / high-reasoning model
agent-cli -p --model opus "Analyze the codebase architecture and write a plan for adding caching..."

# Implement with Sonnet / balanced model
agent-cli -p "Implement the caching layer according to the plan in docs/caching-plan.md..."

# Review with Opus / high-reasoning model
agent-cli -p --model opus "Review all changes for security issues, race conditions, and edge cases..."
```

**With environment context:**
```bash
# Pass context via files, not prompt length
echo "Focus areas: auth module, API rate limiting" > .agent-context.md
agent-cli -p "Read .agent-context.md for priorities. Work through them in order."
rm .agent-context.md
```

**With tool restrictions:**
```bash
# Read-only analysis pass
agent-cli -p --allowedTools "Read,Grep,Glob" "Audit this codebase for security vulnerabilities..."

# Write-only implementation pass
agent-cli -p --allowedTools "Read,Write,Edit,Bash" "Implement the fixes from security-audit.md..."
```

---

## 2. NanoClaw / Persistent REPL

**Persistent loop architecture.** A session-aware REPL that invokes the agent synchronously with full conversation history stored in structured markdown.

```bash
# Start the default session
node scripts/claw.js

# Named session with skill context
CLAW_SESSION=my-project CLAW_SKILLS=tdd-workflow,security-review node scripts/claw.js
```

### How It Works

1. Loads conversation history from `~/.gemini/claw/{session}.md`
2. Each user message is sent to the execution engine with full history as context
3. Responses are appended to the session file (Markdown-as-database)
4. Sessions persist across restarts

### When Persistent REPL vs Sequential Pipeline

| Use Case | Persistent REPL | Sequential Pipeline |
|----------|-----------------|-------------------|
| Interactive exploration | Yes | No |
| Scripted automation | No | Yes |
| Session persistence | Built-in | Manual |
| Context accumulation | Grows per turn | Fresh each step |
| CI/CD integration | Poor | Excellent |

---

## 3. Infinite Agentic Loop

**A two-prompt system** that orchestrates parallel sub-agents for specification-driven generation. Developed by disler (credit: @disler).

### Architecture: Two-Prompt System

```
PROMPT 1 (Orchestrator)              PROMPT 2 (Sub-Agents)
┌─────────────────────┐             ┌──────────────────────┐
│ Parse spec file      │             │ Receive full context  │
│ Scan output dir      │  deploys   │ Read assigned number  │
│ Plan iteration       │────────────│ Follow spec exactly   │
│ Assign creative dirs │  N agents  │ Generate unique output │
│ Manage waves         │             │ Save to output dir    │
└─────────────────────┘             └──────────────────────┘
```

### The Pattern

1. **Spec Analysis** - Orchestrator reads a specification file (Markdown) defining what to generate.
2. **Directory Recon** - Scans existing output to find the highest iteration number.
3. **Parallel Deployment** - Launches N sub-agents, each with:
   - The full spec
   - A unique creative direction
   - A specific iteration number (no conflicts)
   - A snapshot of existing iterations (for uniqueness)
4. **Wave Management** - For infinite mode, deploys waves of 3-5 agents until context is exhausted.

### Implementation via Agent Commands

Create `commands/infinite.md`:

```markdown
Parse the following arguments from $ARGUMENTS:
1. spec_file - path to the specification markdown
2. output_dir - where iterations are saved
3. count - integer 1-N or "infinite"

PHASE 1: Read and deeply understand the specification.
PHASE 2: List output_dir, find highest iteration number. Start at N+1.
PHASE 3: Plan creative directions - each agent gets a DIFFERENT theme/approach.
PHASE 4: Deploy sub-agents in parallel (Task tool). Each receives:
  - Full spec text
  - Current directory snapshot
  - Their assigned iteration number
  - Their unique creative direction
PHASE 5 (infinite mode): Loop in waves of 3-5 until context is low.
```

### Batching Strategy

| Count | Strategy |
|-------|----------|
| 1-5 | All agents simultaneously |
| 6-20 | Batches of 5 |
| infinite | Waves of 3-5, progressive sophistication |

### Key Insight: Uniqueness via Assignment

Don't rely on agents to self-differentiate. The orchestrator **assigns** each agent a specific creative direction and iteration number. This prevents duplicate concepts across parallel agents.

---

## 4. Continuous PR Loop

**A production-grade loop** that runs the agent in a continuous iteration cycle, creating PRs, waiting for CI, and merging automatically. Created by AnandChowdhary (credit: @AnandChowdhary).

### Core Loop

```
┌─────────────────────────────────────────────────────┐
│  CONTINUOUS ITERATION LOOP                          │
│                                                     │
│  1. Create branch (continuous/iteration-N)          │
│  2. Run agent with enhanced prompt                  │
│  3. (Optional) Reviewer pass - separate agent       │
│  4. Commit changes (agent generates message)        │
│  5. Push + create PR (gh pr create)                 │
│  6. Wait for CI checks (poll gh pr checks)          │
│  7. CI failure? → Auto-fix pass                     │
│  8. Merge PR (squash/merge/rebase)                  │
│  9. Return to main → repeat                         │
│                                                     │
│  Limit by: --max-runs N | --max-cost $X             │
│            --max-duration 2h | completion signal     │
└─────────────────────────────────────────────────────┘
```

### Usage

```bash
# Basic: 10 iterations
continuous-agent --prompt "Add unit tests for all untested functions" --max-runs 10

# Cost-limited
continuous-agent --prompt "Fix all linter errors" --max-cost 5.00

# Time-boxed
continuous-agent --prompt "Improve test coverage" --max-duration 8h

# With code review pass
continuous-agent \
  --prompt "Add authentication feature" \
  --max-runs 10 \
  --review-prompt "Run npm test && npm run lint, fix any failures"

# Parallel via worktrees
continuous-agent --prompt "Add tests" --max-runs 5 --worktree tests-worker &
continuous-agent --prompt "Refactor code" --max-runs 5 --worktree refactor-worker &
wait
```

### Cross-Iteration Context: SHARED_TASK_NOTES.md

The critical innovation: a `SHARED_TASK_NOTES.md` file persists across iterations:

```markdown
## Progress
- [x] Added tests for auth module (iteration 1)
- [x] Fixed edge case in token refresh (iteration 2)
- [ ] Still need: rate limiting tests, error boundary tests

## Next Steps
- Focus on rate limiting module next
- The mock setup in tests/helpers.ts can be reused
```

The agent reads this file at iteration start and updates it at iteration end. This bridges the context gap between independent invocations.

### CI Failure Recovery

When PR checks fail, the loop automatically:
1. Fetches the failed run ID via `gh run list`
2. Spawns a new agent process with CI fix context
3. Agent inspects logs via `gh run view`, fixes code, commits, pushes
4. Re-waits for checks (up to `--ci-retry-max` attempts)

### Completion Signal

The agent can signal "I'm done" by outputting a magic phrase:

```bash
continuous-agent \
  --prompt "Fix all bugs in the issue tracker" \
  --completion-signal "PROJECT_COMPLETE" \
  --completion-threshold 3  # Stops after 3 consecutive signals
```

Three consecutive iterations signaling completion stops the loop, preventing wasted runs on finished work.

---

## 5. The De-Sloppify Pattern

**An add-on pattern for any loop.** Add a dedicated cleanup/refactor step after each Implementer step.

### The Problem

When you ask an LLM to implement with TDD, it takes "write tests" too literally:
- Tests that verify the language type system works (testing `typeof x === 'string'`)
- Overly defensive runtime checks for things the type system already guarantees
- Tests for framework behavior rather than business logic
- Excessive error handling that obscures the actual code

### Why Not Negative Instructions?

Adding "don't test type systems" or "don't add unnecessary checks" to the Implementer prompt has downstream effects:
- The model becomes hesitant about ALL testing
- It skips legitimate edge case tests
- Quality degrades unpredictably

### The Solution: Separate Pass

Instead of constraining the Implementer, let it be thorough. Then add a focused cleanup agent:

```bash
# Step 1: Implement (let it be thorough)
agent-cli -p "Implement the feature with full TDD. Be thorough with tests."

# Step 2: De-sloppify (separate context, focused cleanup)
agent-cli -p "Review all changes in the working tree. Remove:
- Tests that verify language/framework behavior rather than business logic
- Redundant type checks that the type system already enforces
- Over-defensive error handling for impossible states
- Console.log statements
- Commented-out code

Keep all business logic tests. Run the test suite after cleanup to ensure nothing breaks."
```

### In a Loop Context

```bash
for feature in "${features[@]}"; do
  # Implement
  agent-cli -p "Implement $feature with TDD."

  # De-sloppify
  agent-cli -p "Cleanup pass: review changes, remove test/code slop, run tests."

  # Verify
  agent-cli -p "Run build + lint + tests. Fix any failures."

  # Commit
  agent-cli -p "Commit with message: feat: add $feature"
done
```

### Key Insight

> Rather than adding negative instructions which have downstream quality effects, add a separate de-sloppify pass. Two focused agents outperform one constrained agent.

---

## 6. Ralphinho / RFC-Driven DAG Orchestration

**The most sophisticated pattern.** An RFC-driven, multi-agent pipeline that decomposes a spec into a dependency DAG, runs each unit through a tiered quality pipeline, and lands them via an agent-driven merge queue. Created by enitrat (credit: @enitrat).

### Architecture Overview

```
RFC/PRD Document
       │
       ▼
  DECOMPOSITION (AI)
  Break RFC into work units with dependency DAG
       │
       ▼
┌──────────────────────────────────────────────────────┐
│  RALPH LOOP (up to 3 passes)                         │
│                                                      │
│  For each DAG layer (sequential, by dependency):     │
│                                                      │
│  ┌── Quality Pipelines (parallel per unit) ───────┐  │
│  │  Each unit in its own worktree:                │  │
│  │  Research → Plan → Implement → Test → Review   │  │
│  │  (depth varies by complexity tier)             │  │
│  └────────────────────────────────────────────────┘  │
│                                                      │
│  ┌── Merge Queue ─────────────────────────────────┐  │
│  │  Rebase onto main → Run tests → Land or evict │  │
│  │  Evicted units re-enter with conflict context  │  │
│  └────────────────────────────────────────────────┘  │
│                                                      │
└──────────────────────────────────────────────────────┘
```

### RFC Decomposition

AI reads the RFC and produces work units:

```typescript
interface WorkUnit {
  id: string;              // kebab-case identifier
  name: string;            // Human-readable name
  rfcSections: string[];   // Which RFC sections this addresses
  description: string;     // Detailed description
  deps: string[];          // Dependencies (other unit IDs)
  acceptance: string[];    // Concrete acceptance criteria
  tier: "trivial" | "small" | "medium" | "large";
}
```

**Decomposition Rules:**
- Prefer fewer, cohesive units (minimize merge risk)
- Minimize cross-unit file overlap (avoid conflicts)
- Keep tests WITH implementation (never separate "implement X" + "test X")
- Dependencies only where real code dependency exists

The dependency DAG determines execution order:
```
Layer 0: [unit-a, unit-b]     ← no deps, run in parallel
Layer 1: [unit-c]             ← depends on unit-a
Layer 2: [unit-d, unit-e]     ← depend on unit-c
```

### Complexity Tiers

Different tiers get different pipeline depths:

| Tier | Pipeline Stages |
|------|----------------|
| **trivial** | implement → test |
| **small** | implement → test → code-review |
| **medium** | research → plan → implement → test → PRD-review + code-review → review-fix |
| **large** | research → plan → implement → test → PRD-review + code-review → review-fix → final-review |

### Separate Context Windows (Author-Bias Elimination)

Each stage runs in its own agent process with its own context window:

| Stage | Purpose |
|-------|---------|
| Research | Read codebase + RFC, produce context doc |
| Plan | Design implementation steps |
| Implement | Write code following the plan |
| Test | Run build + test suite |
| PRD Review | Spec compliance check |
| Code Review | Quality + security check |
| Review Fix | Address review issues |
| Final Review | Quality gate (large tier only) |

**Critical design:** The reviewer never wrote the code it reviews. This eliminates author bias - the most common source of missed issues in self-review.

### Merge Queue with Eviction

After quality pipelines complete, units enter the merge queue:

```
Unit branch
    │
    ├─ Rebase onto main
    │   └─ Conflict? → EVICT (capture conflict context)
    │
    ├─ Run build + tests
    │   └─ Fail? → EVICT (capture test output)
    │
    └─ Pass → Fast-forward main, push, delete branch
```

**Eviction Recovery:**
When evicted, full context is captured (conflicting files, diffs, test output) and fed back to the implementer on the next Ralph pass:

```markdown
## MERGE CONFLICT - RESOLVE BEFORE NEXT LANDING

Your previous implementation conflicted with another unit that landed first.
Restructure your changes to avoid the conflicting files/lines below.

{full eviction context with diffs}
```

---

## 7. Antigravity Background Hooks & Cognitive Dream Mode

Kortext complements interactive and terminal loops with native system background daemons and asynchronous sidecars.

### Background Hooks & Daemons Architecture

```
┌──────────────────────────────────────────────────────────────┐
│                    ANTIGRAVITY HARNESS                       │
├──────────────────────────────┬───────────────────────────────┤
│ Active Interactive Session   │ Background Substrate Daemons  │
│  • seek_symbol AST Queries   │  • File Watcher (watchdog)    │
│  • replace_file_content      │  • FalkorDB Graph Server      │
│  • pytest Verification       │  • Qdrant Vector Engine       │
│  • manage_tasks DAG state    │  • Cognitive Dream Consolidation
└──────────────────────────────┴───────────────────────────────┘
```

1. **Continuous Filesystem Watcher (`kortext-watcher`):**
   Monitors workspace file modifications via `watchdog`. Whenever code is saved, background hooks queue incremental Tree-sitter AST re-indexing and SCIP call-graph extraction without blocking active user sessions.

2. **Cognitive Dream Mode (`kortext-dream`):**
   When the workstation or agent enters idle periods, background sidecars trigger deep semantic consolidation:
   - Sweeps episodic memory journals (`journal/*.json`).
   - Clusters disconnected concepts using Louvain community detection.
   - Computes HippoRAG personalized PageRank weights across the dual knowledge graph.
   - Prunes superseded facts and stabilizes bi-temporal assertions.

3. **Background Task Management via `manage_tasks`:**
   In Kortext, long-running background tasks or subagent swarms register in FalkorDB:
   ```python
   manage_tasks(
       action="create",
       task_id="loop_sweep_01",
       title="Background HippoRAG Graph Consolidation",
       description="Run offline personalized PageRank updates across all entity nodes",
       dependencies=[]
   )
   ```

---

## Choosing the Right Pattern

### Decision Matrix

```
Is the task a single focused change?
├─ Yes → Sequential Pipeline or NanoClaw
└─ No → Is there a written spec/RFC?
         ├─ Yes → Do you need parallel implementation?
         │        ├─ Yes → Ralphinho (DAG orchestration)
         │        └─ No → Continuous PR Loop (iterative dev loop)
         └─ No → Do you need many variations of the same thing?
                  ├─ Yes → Infinite Agentic Loop (spec-driven generation)
                  └─ No → Sequential Pipeline with de-sloppify
```

### Combining Patterns

1. **Sequential Pipeline + De-Sloppify** - The most common combination. Every implement step gets a cleanup pass.
2. **Continuous Loop + De-Sloppify** - Add a review prompt with a de-sloppify directive to each iteration.
3. **Any loop + Verification** - Use `verification-loop` as a gate before commits.
4. **Ralphinho + Kortext Task DAG** - Back the work unit queue using FalkorDB `manage_tasks` for multi-session durability.

---

## Anti-Patterns

1. **Infinite loops without exit conditions** - Always configure max-runs, max-cost, max-duration, or completion signals.
2. **No context bridge between iterations** - Each non-interactive agent call starts fresh. Use `SHARED_TASK_NOTES.md` or Kortext `memory_session_handoff` to bridge context.
3. **Retrying the same failure** - If an iteration fails, don't just retry. Capture the error context and feed it to the next attempt.
4. **Negative instructions instead of cleanup passes** - Don't say "don't do X." Add a separate pass that removes X.
5. **All agents in one context window** - For complex workflows, separate concerns into different agent processes. The reviewer should never be the author.
6. **Ignoring file overlap in parallel work** - If two parallel agents might edit the same file, you need a merge strategy (sequential landing, rebase, or conflict resolution).

---

## References

| Project | Author | Context |
|---------|--------|---------|
| Ralphinho | enitrat | RFC-driven DAG orchestration with merge queue |
| Infinite Agentic Loop | disler | Two-prompt orchestrator/worker pattern |
| Continuous Claude | AnandChowdhary | Iterative PR loop with CI recovery |
| NanoClaw | ECC | Markdown-as-database persistent REPL |
| Kortext Dream Mode | Kortext | Background memory consolidation & HippoRAG |
| Verification Loop | ECC / Kortext | Multi-phase pre-commit and pre-persistence gates |
