---
name: codebase-onboarding
description: Analyze an unfamiliar codebase and produce a structured onboarding guide with architecture map, key entry points, conventions, and starter instructions. Uses AST symbol seeking (seek_symbol) and RAG discovery (search_knowledge_and_memory) instead of ripgrep file hunting.
version: 2.0.0
triggers:
  - "onboard codebase"
  - "understand codebase"
  - "codebase walkthrough"
  - "explore project"
  - "generate instructions"
metadata:
  origin: ECC
  adapted_for: Kortext
---

# Codebase Onboarding

Systematically analyze an unfamiliar codebase and produce a structured onboarding guide. Designed for developers joining a new project or setting up agent instructions in an existing repo for the first time.

## When to Use

- First time opening a project or workspace
- Joining a new team or repository
- User asks "help me understand this codebase"
- User asks to generate a `CLAUDE.md` or `AGENTS.md` for a project
- User says "onboard me" or "walk me through this repo"

---

## The 4-Phase Onboarding Methodology

```
┌────────────────────────────────────────────────────────┐
│  Phase 1: Reconnaissance                               │
│  Manifests, frameworks, configs, and seek_symbol AST   │
├────────────────────────────────────────────────────────┤
│  Phase 2: Architecture Mapping                         │
│  Tech stack, data flow, search_knowledge_and_memory    │
├────────────────────────────────────────────────────────┤
│  Phase 3: Convention Detection                         │
│  Naming, error styles, test patterns, git workflow     │
├────────────────────────────────────────────────────────┤
│  Phase 4: Generate Onboarding Artifacts                │
│  Output 1: Onboarding Guide                            │
│  Output 2: Starter AGENTS.md / CLAUDE.md               │
└────────────────────────────────────────────────────────┘
```

---

### Phase 1: Reconnaissance

Gather raw signals about the project without reading every file. Avoid unconstrained regex scans (`grep -r`, `rg .`) that cause token bleed; run targeted checks:

```
1. Package manifest detection
   → pyproject.toml, package.json, go.mod, Cargo.toml, pom.xml,
     build.gradle, Gemfile, composer.json, mix.exs

2. Framework fingerprinting
   → next.config.*, vite.config.*, angular.json, fastapi bootstrap,
     flask app factory, django settings, rails config

3. Entry point identification via seek_symbol
   → seek_symbol(symbol_name="main")
   → seek_symbol(symbol_name="create_app")
   → seek_symbol(symbol_name="app")
   → seek_symbol(symbol_name="server")

4. Directory structure snapshot
   → Top 2 levels of the directory tree, ignoring node_modules,
     vendor, .git, dist, build, __pycache__, .next

5. Config and tooling detection
   → tsconfig.json, ruff.toml, .eslintrc*, Makefile, Dockerfile,
     docker-compose*, .github/workflows/, .env.example

6. Test structure detection
   → tests/, test/, __tests__/, *_test.go, *.spec.ts, *.test.ts,
     pytest.ini, jest.config.*, vitest.config.*
```

---

### Phase 2: Architecture Mapping

From the reconnaissance data and Kortext RAG memory, identify:

**Tech Stack**
- Language(s) and version constraints
- Framework(s) and major libraries
- Database(s) and ORMs
- Build tools, package managers (`uv`, `pnpm`, `cargo`)
- CI/CD platform

**Episodic Memory Query (RAG Discovery)**
Check persistent memory for existing architecture decisions:
```python
search_knowledge_and_memory(
    query="architecture overview and core subsystems",
    collection="kortext"
)
```

**Architecture Pattern**
- Monolith, monorepo, microservices, or serverless
- Frontend/backend split or full-stack
- API style: REST, GraphQL, FastMCP, gRPC, tRPC

**Key Directories**
Map top-level directories to their purpose:
```
src/core/        → Core domain models and business invariants
src/api/         → API route handlers and MCP tools
src/storage/     → Database clients, repositories, and caches
tests/           → Unit, integration, and E2E test suites
scripts/         → Build, verification, and migration scripts
```

**Data Flow**
Trace one request from entry to response:
- Where does a request enter? (router, handler, tool registration)
- How is it validated? (middleware, schemas, Pydantic, Zod)
- Where is business logic? (services, models, use cases)
- How does it reach storage? (ORM, raw queries, repositories, UDS socket)

---

### Phase 3: Convention Detection

Identify patterns the codebase already follows:

**Naming Conventions**
- File naming: kebab-case, camelCase, PascalCase, snake_case
- Component/class naming patterns
- Test file naming: `test_*.py`, `*.test.ts`, `*.spec.ts`, `*_test.go`

**Code Patterns**
- Error handling style: try/catch, Result types, custom error hierarchies
- Dependency injection or direct imports
- State management approach
- Async patterns: async/await, coroutines, thread executors

**Git Conventions**
- Branch naming from recent branches (`feature/`, `fix/`)
- Commit message style (Conventional Commits, imperative mood)
- PR workflow (squash, merge, rebase)

---

### Phase 4: Generate Onboarding Artifacts

Produce two structured outputs:

#### Output 1: Onboarding Guide

```markdown
# Onboarding Guide: [Project Name]

## Overview
[2-3 sentences: what this project does and who it serves]

## Tech Stack
| Layer | Technology | Version |
|-------|-----------|---------|
| Language | TypeScript / Python | 5.x / 3.11+ |
| Framework | Next.js / FastMCP | 14.x / 2.x |
| Database | PostgreSQL / FalkorDB | 16 / Redis |
| Testing | Vitest / Pytest | - |

## Architecture
[Description of how components connect]

## Key Entry Points
- **API routes**: `src/api/` - Route handlers
- **Substrates**: `src/storage/` - Data repositories
- **Config**: `pyproject.toml` or `package.json`

## Directory Map
[Top-level directory → purpose mapping]

## Request Lifecycle
[Trace one API request from entry to response]

## Conventions
- [File naming pattern]
- [Error handling approach]
- [Testing patterns]
- [Git workflow]

## Common Tasks
- **Run dev server**: `npm run dev` or `uv run dev`
- **Run tests**: `npm test` or `pytest`
- **Run linter**: `npm run lint` or `ruff check .`
- **Build**: `npm run build`

## Where to Look
| I want to... | Look at... |
|--------------|-----------|
| Add an endpoint | `src/api/` |
| Add a model | `src/models/` |
| Add a test | `tests/` |
```

#### Output 2: Starter AGENTS.md / CLAUDE.md

Generate or update project instructions based on detected conventions:

```markdown
# Project Instructions

## Tech Stack
[Detected stack summary]

## Code Style
- [Detected naming conventions]
- [Detected patterns to follow]

## Testing
- Run tests: `[detected test command]`
- Test pattern: [detected test file convention]
- Coverage: [coverage command]

## Build & Run
- Dev: `[detected dev command]`
- Build: `[detected build command]`
- Lint: `[detected lint command]`

## Project Structure
[Key directory → purpose map]

## Conventions
- [Commit style]
- [PR workflow]
- [Error handling patterns]
```

---

## Best Practices

1. **Don't read everything** - reconnaissance should use `seek_symbol` and targeted file slices, not dumping entire repositories.
2. **Verify, don't guess** - if a framework is detected from config but code uses something different, trust the code.
3. **Respect existing instructions** - if `AGENTS.md` or `CLAUDE.md` already exists, enhance it rather than overwriting blindly.
4. **Stay concise** - the onboarding guide should be scannable in 2 minutes.
5. **Flag unknowns** - if a convention cannot be confidently detected, state it clearly rather than guessing.

---

## Anti-Patterns to Avoid

- Generating instructions longer than 100 lines - keep them focused.
- Listing every minor dependency - highlight only what shapes how code is authored.
- Describing obvious directories - `src/` doesn't need an essay.
- Copying the README - the onboarding guide provides structural insight the README lacks.
- Brute-force ripgrep scanning - use `seek_symbol` for AST-accurate declarations.

---

## Examples

### Example 1: First time in a new repo
**User**: "Onboard me to this codebase"  
**Action**: Run 4-phase workflow → produce Onboarding Guide + Starter instructions.

### Example 2: Generate project instructions for existing project
**User**: "Generate an AGENTS.md for this project"  
**Action**: Run Phases 1-3, skip guide, produce only instructions file.

### Example 3: Enhance existing instructions
**User**: "Update the project instructions with current conventions"  
**Action**: Read existing instructions, run Phases 1-3, merge findings.
