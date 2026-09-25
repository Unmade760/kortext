---
name: verification-loop
description: Pre-persistence verification protocol ensuring memory assertions and code changes pass tests before recording.
version: 1.0.0
triggers:
  - "verify before record"
  - "run verification"
  - "pre-flight check"
---

# Pre-Persistence Verification Protocol

## Mandatory Verification Sequence:
1. **Lint & Static Check:** Run project linter or type check on modified files.
2. **Targeted Unit Test:** Execute unit tests covering the exact modified symbols (`pytest tests/test_<symbol>.py`).
3. **AST Invariant Check:** Verify that modified signatures have not broken upstream callers via `trace_symbol_impact`.
4. **Outcome Persistence:** Call `record_system_outcome` ONLY after all 3 checks report PASS.
