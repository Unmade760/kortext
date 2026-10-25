---
name: systematic-debugging
description: Use when diagnosing any bug, test failure, crash, flaky behavior, or unexpected output before proposing or applying a fix.
---

# Systematic Root-Cause Debugging Protocol

Enforces root-cause investigation before any code modification, pairing red-capable reproduction loops, AST backward call-graph tracing (`trace_symbol_impact`), tagged diagnostic probes, and a hard 3-Fix Circuit Breaker.

## 1. The Iron Law of Debugging

> **NO FIXES WITHOUT ROOT CAUSE INVESTIGATION FIRST.**
> Symptom patches (`try/except Exception: pass`, coercing `None` at the UI/caller boundary, or tweaking test assertions) are failures. Trace the invalid state backward to the exact architectural seam where it originated.

## 2. The 6-Phase Debugging Lifecycle

| Phase | Objective | Exact Action & Tooling |
|---|---|---|
| **1. Red Feedback Loop** | Reproduce the exact failure deterministically in `<5s` | Run `uv run pytest path/to/test.py -k test_name -q` asserting the exact exception/symptom before touching source code. |
| **2. AST Backward Trace** | Trace data flow from failure site to origin in `<10ms` | Run `seek_symbol(symbol_name="failing_fn")` and `trace_symbol_impact(symbol="failing_fn", direction="upstream")`. **Never run `rg` sweeps.** |
| **3. Minimise Reproduction** | Strip all non-load-bearing inputs and mocks | Remove parameters one by one until only the minimal input triggering the exact stack trace remains. |
| **4. Ranked Hypotheses** | Formulate 3–5 falsifiable hypotheses | State: *"If [Root Cause X] is true, then [Minimal Check Y] will produce [Outcome Z]."* Test **one variable at a time**; revert immediately if falsified. |
| **5. Tagged Probes (`[DEBUG-xxxx]`)** | Observe runtime state when static trace is insufficient | Log actual values and types with a unique session tag (`logger.info("[DEBUG-9a1f] val=%r type=%s", v, type(v))`). Remove all `[DEBUG-...]` lines before commit (`git diff \| grep DEBUG`). |
| **6. TDD Seam Fix** | Fix at the origin seam with a regression test | Write failing unit test at the origin seam (RED) $\rightarrow$ minimal immutable fix (GREEN) $\rightarrow$ full suite `uv run pytest -q`. |

## 3. The 3-Fix Circuit Breaker (Hard Stop)

If **3 consecutive fix attempts fail** to resolve the bug or introduce new failures:
1. **HALT IMMEDIATELY**: Do not attempt Fix #4. Three failed fixes prove your mental model of the subsystem or architectural seam is wrong.
2. **Revert to Clean Baseline**: Run `git checkout -- <modified_files>` so failed experiments never accumulate.
3. **Question Foundational Assumptions**: Check `check_kortext_health()` (is FalkorDB/Qdrant/oMLX returning stale or degraded state?), inspect `trace_symbol_impact(..., direction="downstream")`, and escalate the 3 falsified hypotheses + stack trace to the user or `kortext-architect`.

## 4. Rationalization Defense Matrix

| Common Excuse | Why It Fails | Mandated Protocol Action |
|---|---|---|
| *"I can see the `NoneType` error right here, I'll just add `if x is None: return []`."* | Masks corrupted upstream state and silently returns empty data to callers. | Run `trace_symbol_impact(..., direction="upstream")` to find why `None` was produced in the first place. |
| *"I'll wrap this block in `try ... except Exception:` so the test passes."* | Swallows real runtime errors and violates Kortext observability and security invariants. | Let typed exceptions propagate or handle the specific expected error class at the protocol boundary. |
| *"Let me change these 3 config values at once to see if it works."* | Multi-variable edits make it impossible to know which change fixed or broke the behavior. | Test one variable at a time; revert before testing the next hypothesis. |
| *"Attempt 3 was super close, just one more tweak will fix it."* | Classic sunk-cost thrashing that corrupts working files. | Trip the **3-Fix Circuit Breaker**, revert speculative diffs, and re-evaluate the architecture. |

## 5. Diagnosing Kortext Harness & Session Telemetry (`diagnosing-kortext`)

When diagnosing why a Kortext lifecycle hook blocked or stayed silent, why a session burned excessive tokens, or why retrieval missed a symbol, inspect the ground-truth telemetry files:
1. **Substrate & Lock Status**: Run `check_kortext_health()` and inspect `~/.kortext/run/hud_state.json`.
2. **Hook & Gate Forensics**: Inspect `~/.kortext/telemetry/tools.jsonl`, `~/.kortext/telemetry/invocations.jsonl`, `~/.kortext/run/last_test_run.json`, and `~/.kortext/quarantine/`.
