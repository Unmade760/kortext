---
trigger: always_on
description: "Mandatory systematic debugging protocol: root cause investigation before fixes, feedback loops, falsifiable hypotheses, and 3-fix circuit breaker."
globs: "**/*"
---

# Systematic Debugging

## The Iron Law

> **NO FIXES WITHOUT ROOT CAUSE INVESTIGATION FIRST.**
> Symptom fixes are failure. If you haven't identified the root cause, you cannot propose or implement fixes.

Never apply speculative patches, blind workarounds, or defensive `try/except` wrappers around symptoms. Every defect is caused by an unbroken causal chain originating from an invalid assumption or faulty state transition. Your task is to trace that chain to its root before proposing any modification.

## Phase 1: Construct a Feedback Loop & Investigate Root Cause

- **Tight, red-capable command:** Construct a deterministic command (failing test, curl script, or fixture CLI invocation) that asserts the exact symptom before touching code.
  - The command MUST fail reliably (100% reproduction rate) and demonstrate the defect.
  - Fast execution: The feedback loop should ideally run in seconds (`uv run pytest path/to/test.py -k <test_name>`).
- **Trace backward through call stack / symbol graph:**
  - Trace backward through call stack / symbol graph from error site to data origin.
  - Use AST navigation (`seek_symbol`, `trace_symbol_impact`) to locate callers, inspect signatures, and trace state transitions without token bleed.
  - Inspect intermediate data transformations between input ingress and failure site.
- **Do not jump to hypotheses without a red-capable command:**
  - Speculation without deterministic reproduction leads to false confidence and ineffective patches.
  - Establish the baseline red command first.

## Phase 2: Reproduce & Minimise

- **Shrink reproduction scenario to smallest load-bearing input:**
  - Shrink reproduction scenario to the smallest load-bearing input where every remaining element is required for failure.
  - Eliminate incidental complexity, extraneous mock configurations, or irrelevant fields.
- **Confirm failure mode matches exact symptom:**
  - Confirm the failure mode matches the exact symptom described.
  - Verify that the error signature (exception class, message, HTTP status code, or assertion failure) precisely matches the reported defect, not an incidental or unrelated error.

## Phase 3: Formulate Ranked, Falsifiable Hypotheses

- **Generate 3-5 ranked hypotheses before testing any:**
  - Generate 3-5 ranked hypotheses before testing any.
  - Rank by plausibility and ease of verification before making any code changes.
  - Explicitly document each hypothesis.
- **Each hypothesis must be falsifiable:**
  - Each hypothesis must be falsifiable: "If X is the cause, then changing Y will make the bug disappear / changing Z will make it worse."
- **Test one variable at a time with minimal changes:**
  - Test one variable at a time with minimal changes.
  - Never change multiple moving parts simultaneously. If a test does not prove or disprove the hypothesis, revert immediately before testing the next.

## Phase 4: Implementation (TDD at Correct Seam)

- **Write failing regression test at the correct architectural seam (red):**
  - Write failing regression test at the correct architectural seam (red).
  - Place the test at the appropriate layer (unit, substrate IPC, or integration route) where the defect originated, not merely at the outermost surface.
  - Confirm the test fails with the expected root-cause error signature.
- **Implement minimal fix addressing the root cause (green):**
  - Implement minimal fix addressing the root cause (green).
  - Write only the code necessary to resolve the root cause.
  - Enforce immutability, strict typing, and explicit error handling per project standards.
  - Avoid defensive over-engineering or speculative side-effects.
- **Tag diagnostic probes with unique prefix:**
  - If adding diagnostic probes, tag every log with a unique prefix (e.g. `[DEBUG-xxxx]`) so cleanup is a single clean sweep.
  - Remove all diagnostic probes before finalizing the commit.

## The 3-Fix Circuit Breaker

- **Stop immediately on 3 consecutive failures:**
  - If 3 consecutive fix attempts fail, STOP immediately.
- **Signal of wrong architecture:**
  - 3+ failures signal a wrong architecture, not a failed hypothesis.
  - Repeated failed patches indicate compounding technical debt and fundamental misunderstanding of substrate state.
- **Question fundamental assumptions:**
  - Question fundamental assumptions and discuss architecture with human partner.
  - Step back, revert uncommitted exploratory code, and re-evaluate foundational invariants.

## Common Rationalizations to Avoid

| Rationalization | Trap | Mandated Action |
|---|---|---|
| **"Quick fix for now, investigate later"** | Symptom masking leaves latent defects and technical debt. | **REJECT.** Symptom fixes are failure; investigate root cause first. |
| **"Issue is simple, don't need process"** | Simple issues have root causes too; unverified assumptions cause simple bugs to recur. | **REJECT.** Construct feedback loop and trace data origin. |
| **"One more fix attempt" (after 2+ failures)** | Sunk cost fallacy leads to hacky workarounds and fragile hacks. | **STOP.** Trigger the 3-Fix Circuit Breaker; stop and question architecture. |
| **"Just wrap it in try/except"** | Swallows errors, silences legitimate signals, and violates error-handling invariants. | **REJECT.** Fix the underlying state invalidity at the root cause. |
