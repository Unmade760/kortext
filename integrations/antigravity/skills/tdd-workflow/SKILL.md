---
name: tdd-workflow
description: Use when implementing any feature, bugfix, or refactor to enforce strict RED-GREEN-REFACTOR test-driven development, 80%+ branch coverage, and Obra anti-rationalization discipline.
---

# Test-Driven Development (TDD) Protocol

Enforces the Iron Law of TDD across all feature implementations, bug fixes, and refactors, combining ECC runner rules with Obra (`obra/superpowers`) anti-rationalization discipline and Kortext `IntegrityModeAuditor` verification.

## 1. The Iron Law of TDD

> **NO PRODUCTION CODE WITHOUT A FAILING TEST FIRST.**
> If you wrote production code before watching the test fail, **delete the production code** and start over from the RED phase.

## 2. The 6-Step RED-GREEN-REFACTOR Lifecycle

| Phase | Action | Verification Gate |
|---|---|---|
| **0. Runner & Target Discovery** | Detect test runner (`uv run pytest`, `pnpm test`, `bun test`, `cargo test`) and inspect target symbols via `seek_symbol(symbol_name="...")`. | Never grep blindly; ground test assertions in exact AST signatures. |
| **1. RED (Write Failing Test)** | Write a minimal test asserting the desired public behavior, edge case, or bug reproduction. | Test **must** compile/import cleanly and fail on the assertion (`AssertionError` / missing symbol), not a syntax error. |
| **2. Verify RED** | Execute the targeted test command (`uv run pytest tests/test_x.py -k test_case -q`). | Confirm expected failure output in terminal. Never skip watching it fail. |
| **3. GREEN (Minimal Code)** | Write only the simplest production code required to pass the failing test. | Zero speculative extras; zero `unittest.mock` or `sys.modules` monkey-patching inside production modules (`IntegrityModeAuditor`). |
| **4. Verify GREEN** | Re-run the targeted test and full suite (`uv run pytest -q`). | 100% green pass rate with zero regressions. |
| **5. REFACTOR & Coverage** | Eliminate duplication, enforce immutability (`frozen=True`), and verify $\ge 80\%$ coverage (`pytest --cov=. --cov-report=term-missing`). | Tests remain 100% green after every refactor edit. |

## 3. Obra Rationalization Defense Table

If you catch yourself thinking any of the following excuses, **STOP** immediately—each is a TDD violation:

| Rationalization Excuse | Why It Fails in Practice | Mandatory Protocol Action |
|---|---|---|
| *"I'll write the tests right after I get the implementation working."* | Tests written after code pass immediately, never proving they can catch the regression, and test implementation details instead of contracts. | Delete the unverified implementation code and write the failing test first. |
| *"This change is too simple / just a 3-line config or model tweak to test first."* | Simple code breaks callers silently; a 3-line change takes 15 seconds to write a failing assertion for. | Write the 5-line test first and watch it fail. |
| *"I already manually tested it via CLI / REPL."* | Manual ad-hoc checks vanish when the session ends and do not guard future refactors. | Codify the exact check into an automated `pytest` / `vitest` test. |
| *"Deleting my working code just to run RED is wasteful sunk cost."* | Unverified code is technical debt, not an asset. If you never saw the test fail, you don't know if the test assertions even run. | Stash or delete the edit, run the test to confirm RED, then restore minimal GREEN code. |
| *"I'll add a mock fallback in production code so the test passes offline."* | Violates `IntegrityModeAuditor` (`demo`/`benchmark` integrity rules) and hides real substrate failures in production. | Keep test doubles strictly inside `tests/`; use explicit Protocol injection at boundaries. |

## 4. Test Quality & Boundary Rules

1. **Test Public Contracts, Not Internals**: Assert inputs, return values, raised exception types (`with pytest.raises(ValueError, match=...):`), and observable state transitions—never private `_helper` implementation details.
2. **Isolate External Substrates via Protocol Seams**: Inject mock/in-memory adapters in `tests/` fixtures; never let unit tests depend on ambient network state or mutate shared global singletons.
3. **Mandatory Edge-Case Matrix**: Every feature test suite must cover: (a) happy path, (b) empty/null/`None` inputs, (c) boundary limits, and (d) upstream substrate timeout or error envelopes.
