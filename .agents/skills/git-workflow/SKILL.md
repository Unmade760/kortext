---
name: git-workflow
description: Git workflow patterns including branching strategies (GitHub Flow, Trunk-Based, GitFlow), conventional commit conventions, merge vs rebase, PR standards, and conflict resolution. Use when managing branches, commits, or pull requests.
version: 2.0.0
triggers:
  - "git workflow"
  - "branching strategy"
  - "conventional commits"
  - "merge vs rebase"
  - "pull request template"
  - "resolve merge conflict"
metadata:
  origin: ECC
  adapted_for: Kortext
---

# Git Workflow Patterns

Best practices for Git version control, branching strategies, commit hygiene, and collaborative development.

## When to Activate

- Setting up Git workflow or branch policies for a project or repository
- Deciding on a branching strategy (GitHub Flow, Trunk-Based, GitFlow)
- Authoring commit messages following Conventional Commits standards
- Deciding between merge commits, rebase, or squash merges
- Resolving merge conflicts cleanly
- Preparing pull requests, code reviews, and semantic releases

---

## Branching Strategies

### 1. GitHub Flow (Simple & Recommended)

Best for continuous deployment, SaaS, and agile teams.

```
main (protected, always deployable)
  │
  ├── feature/user-auth      → PR → merge to main
  ├── feature/payment-flow   → PR → merge to main
  └── fix/login-bug          → PR → merge to main
```

**Rules:**
- `main` is protected and always deployable.
- Feature branches branch off from `main`.
- Open a Pull Request early for feedback or when ready for review.
- After passing CI checks and review approval, merge into `main`.
- Deploy immediately after merging.

---

### 2. Trunk-Based Development (High Velocity)

Best for teams with strong test automation and feature flags.

```
main (trunk)
  │
  ├── short-lived branch (1-2 days max)
  ├── short-lived branch
  └── short-lived branch
```

**Rules:**
- Developers commit to `main` or very short-lived branches (< 48 hours).
- Incomplete features are hidden behind runtime feature flags.
- Comprehensive CI test suites must pass before merge.
- Deployments happen multiple times per day.

---

### 3. GitFlow (Scheduled Releases)

Best for enterprise software, mobile apps, or regulated environments with formal release cycles.

```
main (production releases)
  │
  └── develop (integration branch)
        │
        ├── feature/user-auth
        ├── release/1.0.0    → merge to main and develop
        └── hotfix/critical  → merge to main and develop
```

---

### Strategy Comparison

| Strategy | Team Size | Release Cadence | Best For |
| :--- | :--- | :--- | :--- |
| **GitHub Flow** | Any | Continuous | Web applications, SaaS, microservices |
| **Trunk-Based** | 5+ experienced | Multiple per day | High-velocity teams with robust CI/CD |
| **GitFlow** | 10+ | Scheduled / milestone | Regulated software, mobile app stores |

---

## Commit Messages & Conventional Commits

### Format

```
<type>(<scope>): <subject>

[optional body explaining motivation and trade-offs]

[optional footer(s): Closes #123, BREAKING CHANGE: ...]
```

### Types

| Type | Purpose | Example |
| :--- | :--- | :--- |
| `feat` | New feature or capability | `feat(auth): add OAuth2 refresh token rotation` |
| `fix` | Bug fix | `fix(cache): resolve TTL expiry race condition` |
| `refactor` | Code restructuring without behavior change | `refactor(db): extract client connection pool` |
| `test` | Adding or updating tests | `test(symbols): add AST seek_symbol unit tests` |
| `perf` | Performance optimization | `perf(search): add composite index on workspace and path` |
| `docs` | Documentation changes | `docs(readme): add installation guide` |
| `chore` | Maintenance, dependencies, config | `chore(deps): update qdrant-client to v1.9.0` |
| `ci` | CI/CD pipeline modifications | `ci: add coverage threshold check to workflow` |
| `revert` | Revert previous commit | `revert: revert "feat(auth): add OAuth2 refresh token"` |

### Good vs Bad Commit Messages

```
# FAIL: Vague, no context
git commit -m "fixed bugs"
git commit -m "WIP"
git commit -m "updated stuff"

# PASS: Clear, explains why, references issue
git commit -m "fix(api): retry requests on 503 Service Unavailable

Upstream FalkorDB socket occasionally drops during heavy background writes.
Added exponential backoff with full jitter and max 3 attempts.

Closes #142"
```

---

## Merge vs Rebase

### Merge Commit (Preserves Full Branch Topology)

```bash
git checkout main
git merge feature/user-auth
```
- **Use when:** Merging feature branches into `main` where full historical branch lifetime is desired.

### Rebase (Linear History)

```bash
git checkout feature/user-auth
git fetch origin
git rebase origin/main
```
- **Use when:** Updating your local feature branch with latest `main` before opening or merging a PR.
- **Pushing after rebase:** `git push --force-with-lease origin feature/user-auth`

### Golden Rule of Rebase
**NEVER rebase branches that have been shared or merged into public repositories.** Rebasing rewrites commit SHA hashes and breaks collaborator histories.

---

## Pull Request Workflow

### PR Description Template

```markdown
## What
Brief summary of the changes introduced.

## Why
Explain the context, problem, or motivation.

## How
Key technical decisions, trade-offs, and implementation details.

## Verification & Testing
- [ ] Unit tests pass (`pytest` / `npm test`)
- [ ] Integration tests pass
- [ ] 80%+ code coverage verified
- [ ] Pre-commit linter checks pass (`ruff` / `eslint`)

Closes #[IssueNumber]
```

### Reviewer Checklist

- [ ] Does the code solve the stated problem cleanly?
- [ ] Are all boundary conditions and error paths handled?
- [ ] Does the change maintain architectural invariants?
- [ ] Are new tests added and existing tests passing?
- [ ] Are there any security or secrets leaks?

---

## Conflict Resolution

### Resolving Conflicts

```bash
# 1. Update and rebase against main
git fetch origin
git rebase origin/main

# 2. Check conflicted files
git status

# 3. View conflict markers:
# <<<<<<< HEAD (code from main)
# =======
# >>>>>>> feature/user-auth (your code)

# 4. Edit file, resolve conflicts, remove markers, test
pytest tests/

# 5. Stage resolved files and continue rebase
git add src/auth/login.ts
git rebase --continue
```

To abort a conflicted rebase:
```bash
git rebase --abort
```

---

## Branch Hygiene & Cleanup

```bash
# Delete local branches that have been merged into main
git branch --merged main | grep -v "^\*\|main" | xargs -n 1 git branch -d

# Prune stale remote-tracking branch references
git fetch --prune

# Stash work in progress
git stash push -m "WIP: auth refactor"
git stash pop
```

---

## Release Management & Semantic Versioning

```
vMAJOR.MINOR.PATCH
  • MAJOR: Breaking API changes
  • MINOR: Backward-compatible new features
  • PATCH: Backward-compatible bug fixes
```

Creating an annotated release tag:
```bash
git tag -a v2.1.0 -m "Release v2.1.0: Add FalkorDB Unix domain socket support"
git push origin v2.1.0
```

---

## Anti-Patterns to Avoid

- **Force Pushing to `main`:** Destroys team history and bypasses CI gates.
- **Committing Secrets:** Never commit `.env`, credentials, or keys (use `.gitignore`).
- **Monolithic "Mega-Commits":** Touching 50 files across 4 unrelated concerns makes reviews impossible.
- **Vague Commit Messages:** Commit titles like "fix", "wip", or "test" destroy audit trails.
- **Long-Lived Feature Branches:** Branches lingering for weeks accumulate painful merge conflicts.
