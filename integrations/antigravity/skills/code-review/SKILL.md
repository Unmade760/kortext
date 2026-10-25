---
name: code-review
description: Use when reviewing git diffs, pull requests, or completed Task DAG nodes, or when asked for a strict/thermo-nuclear code quality and maintainability review before commit or outcome persistence.
---

# Multi-Axis & Thermo-Nuclear Code Review Protocol

Unifies standard 6-axis pre-commit/pre-persistence code review (`kortext-code-reviewer`), Author-Blind verification, AST blast-radius auditing (`trace_symbol_impact`), and `--strict` (**Thermo-Nuclear Mode**) structural simplification.

## 1. Author-Blind 5-Step Review Pipeline

1. **Ground Strictly in Artifacts (Ignore Self-Reports)**: Never trust the implementer subagent's prose claims. Inspect only: (a) the task brief/spec, (b) `git diff --staged` / `git diff $BASE_COMMIT...HEAD` (or run the bundled black-box verifier: `python3 ~/.gemini/config/plugins/kortext/skills/code-review/scripts/verify_diff.py --strict`), and (c) freshly executed `uv run pytest -q` output.
2. **AST Blast Radius & Invariant Drift Check (`<10ms`)**:
   - Locate modified symbols via `seek_symbol(symbol_name="<Target>")`.
   - Run `trace_symbol_impact(symbol="<Target>", direction="upstream", max_depth=3)` to verify every caller matches any updated signature or return contract.
3. **Read Surrounding Context (20–50 Lines)**: Check outer caller guards, framework exception handlers, and Pydantic/type validators before flagging missing checks.
4. **Evaluate Against the 6-Axis Matrix** (and **Thermo-Nuclear Rules** when `--strict` or structural review is requested).
5. **Apply the >80% Confidence Pre-Report Gate**: Discard any finding where you cannot cite the exact `file:line`, concrete trigger input, failure state, and why caller guards fail. Zero findings (`APPROVE`) is the expected outcome for clean diffs.

## 2. The 6-Axis Audit Matrix

| Axis | Pass Criteria | Blocking Violations (`CRITICAL` / `HIGH`) |
|---|---|---|
| **1. Spec & Correctness** | Meets all acceptance criteria; strict typing; async/await hygiene | Off-by-one/logic bugs, blocking I/O in async loop, swallowed `except Exception: pass` |
| **2. Blast Radius & AST** | All `trace_symbol_impact` upstream callers compatible | Broken caller signatures, circular imports, unverified `grounds_to` invariant drift |
| **3. Security & MINJA** | Parameterized Cypher/SQL (`$param`), `CausalSanitizer` enforced, `shell=False` | Hardcoded secrets, f-string Cypher/SQL, path traversal, MINJA bypass |
| **4. Kortext Invariants** | Sole Custodian respected, UDS socket (`~/.kortext/run/falkordb.sock`) with TCP fallback | Direct embedded `QdrantClient(path=...)` in hooks/scripts, production `unittest.mock` |
| **5. Test Verification** | Fresh `pytest` exit code `0`, $\ge 80\%$ coverage on new branches, edge cases tested | Failing tests, skipped RED-GREEN proof, tautological assertions (`assert True`) |
| **6. Structure (`--strict`)** | Functions $<50$ lines, files $<800$ lines (hard block crossing $1,000$ lines), $\le 3$ indents | Spaghetti special-case branches, thin pass-through wrappers, duplicate helpers |

## 3. `--strict` / Thermo-Nuclear Mode (Code-Judo Simplification)

Activate automatically on large refactors, files approaching 800–1,000 lines, or when the user asks for a **strict / thermo-nuclear review**:
1. **Hunt for "Code Judo" Moves**: Do not settle for cosmetic cleanup. Look for a structural reframing or data-model change that deletes whole branches, boolean flags, helper layers, or special-case conditionals entirely.
2. **Hard 1,000-Line File Ceiling**: Block any PR that pushes a file across 1,000 lines (or bloats an 800+ line module) when a clean module extraction exists.
3. **Reject Spaghetti Condition Growth**: Block ad-hoc `if` branches bolted onto busy shared flows or feature logic leaking out of its canonical layer. Push logic into a dedicated policy object, dispatch table, or pure helper.
4. **Delete Indirection & Cast Churn**: Flag identity wrappers, unnecessary `Any`/`cast`/optionality that obscures the real type boundary, and bespoke utilities that duplicate an existing canonical helper.

## 4. Common False Positives to Skip

- **Framework/Boundary Guarantees**: Do not flag missing `try/except` or input validation on internal `_helper` functions when FastAPI/FastMCP/Pydantic validates at ingress.
- **Self-Evident Constants**: Do not flag HTTP codes (`200`, `404`, `500`), default ports (`6379`, `6333`, `8000`), or exit codes (`0`, `1`) as "magic numbers".
- **Test Fixtures**: Do not flag dummy credentials or localhost URLs inside `tests/`.

## 5. Standard Review Output Format

```markdown
## Code Review Summary (`Verdict: APPROVE | WARN | BLOCK`)
| Severity | Count | Key Observation |
|---|---|---|
| CRITICAL / HIGH | 0 | Zero security, blast-radius, or invariant violations |
| MEDIUM / LOW | 0 | Clean structure and >=80% test coverage verified |

### [SEVERITY] Finding Title (`path/to/file.py:42-48` | Confidence: 95%)
- **Failure Scenario**: Exact input + state + broken caller/outcome (verified via `trace_symbol_impact`).
- **Code-Judo / Remediation**:
```python
# Drop-in replacement snippet
```
```
