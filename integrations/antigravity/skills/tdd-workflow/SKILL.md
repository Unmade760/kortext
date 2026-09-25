---
name: tdd-workflow
description: Test-driven regression protocol for Task DAG and graph state machines.
version: 1.0.0
triggers:
  - "tdd"
  - "test driven"
  - "write test first"
---

# Test-Driven Development Protocol

## Directives:
1. Write failing test reproducing the defect or specifying the new feature in `tests/`.
2. Verify test failure via `pytest`.
3. Implement surgical minimal changes using `replace_file_content`.
4. Re-run tests until green. Never record outcome until tests pass 100%.
