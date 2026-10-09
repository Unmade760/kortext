---
trigger: always_on
description: "Git commit conventions, branch management, pull request standards, and pre-commit verification."
globs: "**/*"
---

# Git Workflow

## Commit Message Format

```
<type>: <description>

<optional detailed body explaining context, rationale, and breaking changes>
```

### Allowed Types
- **`feat`**: A new feature, capability, or user-facing enhancement.
- **`fix`**: A bug fix or defect remediation.
- **`refactor`**: Code restructuring without behavioral changes.
- **`docs`**: Documentation updates or comment adjustments.
- **`test`**: Adding, modifying, or refactoring test suites.
- **`chore`**: Maintenance tasks, dependency bumps, or tool configurations.
- **`perf`**: Performance optimizations and memory reductions.
- **`ci`**: CI/CD pipeline, build scripts, or daemon automation changes.

### Conventions
- Write the summary line in the imperative mood (e.g., `feat: implement AST symbol seek` instead of `feat: implemented AST symbol seek`).
- Keep the summary line under 72 characters.
- Explain the *why* and *architectural context* in the commit body, not just the *what*.

## Pre-Commit Verification Gate

Before staging, committing, or pushing changes:
1. **Execute Test Suite:**
   ```bash
   uv run pytest -q
   ```
   100% of tests must pass with zero errors.
2. **Validate Manifests:**
   If modifying plugin configs, hooks, agents, or skills:
   ```bash
   python3 scripts/test_plugin_manifest.py
   ```
3. **Verify Kortext Invariants:**
   - [ ] No `ripgrep` / broad regex usage for symbols; AST `seek_symbol` used.
   - [ ] Task DAG and subagent delegation followed for multi-file / $C \ge 4$ work.
   - [ ] Substrate access strictly via UDS/TCP and FastMCP Sole Custodian.
4. **Security Checklist:**
   - [ ] No hardcoded secrets or credentials committed.
   - [ ] All inputs validated; queries parameterized.

## Pull Request Workflow

When preparing a Pull Request:
1. **Analyze History:** Review the complete branch commit history (`git log -n 10 --oneline`).
2. **Review Full Diff:** Inspect the unified diff against the target branch (`git diff [base-branch]...HEAD`) to ensure no unintended modifications or debugging artifacts exist.
3. **Draft Comprehensive Summary:** Structure the PR description with:
   - **Problem / Goal:** Why this change is necessary.
   - **Key Changes:** Bulleted breakdown of major modifications.
   - **Invariants & Architecture:** Notes on architectural decisions and substrate resilience.
   - **Test Plan & Evidence:** Commands executed and pass summary.
4. **Push Upstream:** Push using the upstream tracking flag:
   ```bash
   git push -u origin <branch-name>
   ```
