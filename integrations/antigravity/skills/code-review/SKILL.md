---
name: code-review
description: Invariant compliance and blast-radius review protocol.
version: 1.0.0
triggers:
  - "review code"
  - "audit diff"
---

# Code Review Protocol

## Directives:
1. Run `trace_symbol_impact` on every modified symbol.
2. Verify against `journal/invariants.md`.
3. Check MINJA trust boundaries and sanitize untrusted inputs.
