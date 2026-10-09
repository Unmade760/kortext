---
trigger: always_on
description: "Core coding style standards: immutability, file organization, error handling, input validation, and code quality."
globs: "**/*"
---

# Coding Style

## Immutability (CRITICAL)

ALWAYS create new objects, NEVER mutate existing ones:

```
// Conceptual pattern
WRONG:   modify(original, field, value) → changes original in-place
CORRECT: update(original, field, value) → returns new copy with change
```

In Python:
- Use `dataclasses.dataclass(frozen=True)` or Pydantic `ConfigDict(frozen=True)`.
- Use `MappingProxyType`, immutable tuples, or return new dictionary copies (`{**orig, "key": val}`).
- Never mutate incoming function parameters.

**Rationale:** Immutable data structures eliminate hidden side effects, guarantee race-free concurrency, simplify state tracking across agent turns, and make unit testing completely deterministic.

## Core Principles

### KISS (Keep It Simple)
- Prefer the simplest implementation that satisfies all acceptance tests.
- Avoid premature optimization and speculative complexity.
- Optimize for clarity, readability, and immediate comprehension over cleverness.

### DRY (Don't Repeat Yourself)
- Extract common logic into focused, reusable utility functions or services.
- Prevent copy-paste drift across handlers and subagents.
- Introduce abstractions only when repetition is concrete and proven, never speculative.

### YAGNI (You Aren't Gonna Need It)
- Do not build speculative features, generic plugin wrappers, or unused parameters.
- Solve the immediate task completely; defer future abstractions until requirements demand them.

## File Organization

**MANY SMALL FILES > FEW LARGE FILES:**
- High cohesion, low coupling.
- **200-400 lines typical**, with **800 lines** as a soft maintainability ceiling for source files.
- Test, generated, and migration files may exceed this ceiling when justified.
- Extract sub-modules, helpers, and utilities whenever a module grows beyond 400 lines.
- Organize directory structures by feature/domain, not by generic technical type.

## Error Handling

ALWAYS handle errors comprehensively and explicitly:
- Handle errors explicitly at every level; never allow unhandled exceptions to crash background loops or daemons.
- Provide clear, user-friendly messages in UI-facing and tool-result code.
- Log detailed error context (input parameters, stack traces, substrate states) server-side.
- **NEVER silently swallow errors:** `except Exception: pass` is strictly prohibited. If an error is safely ignorable, log a debug statement explaining why.

## Input Validation

ALWAYS validate at system boundaries:
- Validate all user input, API parameters, and tool payloads before processing.
- Use schema-based validation (Pydantic models, JSON schema, type assertions).
- Fail fast with explicit, actionable error messages.
- Never trust external data (HTTP responses, user-provided file content, environment variables).

## Naming Conventions

- **Descriptive Names:** The identifier name must clearly state what the entity holds or does without requiring an inline comment.
- **Booleans:** Name boolean variables and flags as clear claims: `is_valid`, `has_token`, `can_execute`, `should_retry`.
- **Constants:** Visual distinction with `UPPER_SNAKE_CASE` for configuration defaults and fixed thresholds.
- **Classes & Types:** `PascalCase`.
- **Functions & Variables:** `snake_case`.

## Code Smells to Avoid

### Deep Nesting
- Avoid conditionals nested beyond 3-4 levels.
- Prefer early returns, guard clauses, and pattern matching to flatten nested control flow.

### Magic Numbers
- Extract numeric thresholds, timeouts, and buffer sizes into named module-level constants.

### Long Functions
- Functions should ideally be under 50 lines.
- Split multi-stage algorithms into well-named private helper functions.

## Code Quality Checklist

Before marking any task complete:
- [ ] Code is readable, well-named, and self-documenting
- [ ] Functions are small (<50 lines)
- [ ] Files are focused (<800 lines, 200-400 lines typical)
- [ ] No deep nesting (>4 levels)
- [ ] Proper error handling at all boundaries (no swallowed exceptions)
- [ ] No hardcoded values (constants or configuration used)
- [ ] No mutation (immutable patterns used)
- [ ] Strict type annotations on all parameters and return values
