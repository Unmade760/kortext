---
name: search-first
description: Research-before-coding workflow. Search for existing tools, libraries, MCPs, patterns, local symbols, and persistent memory before writing custom code.
version: 2.0.0
triggers:
  - "search first"
  - "research before coding"
  - "find existing solution"
  - "check existing tools"
metadata:
  origin: ECC
  adapted_for: Kortext
---

# /search-first - Research Before You Code

Systematizes the "search for existing solutions before implementing" workflow to eliminate redundant code authoring and prevent reinventing existing patterns.

## Trigger

Use this skill when:
- Starting a new feature that likely has existing open-source or internal solutions
- Adding a dependency, integration, or MCP tool
- The user asks "add X functionality" and you're about to write code
- Before creating a new utility, helper, or architectural abstraction

---

## Workflow

```
┌─────────────────────────────────────────────────────────┐
│  0. TOOL AVAILABILITY PREFLIGHT                         │
│     Check search channels before relying on them;       │
│     report skipped channels honestly                    │
├─────────────────────────────────────────────────────────┤
│  1. NEED ANALYSIS                                       │
│     Define what functionality is needed                 │
│     Identify language/framework constraints             │
├─────────────────────────────────────────────────────────┤
│  2. PARALLEL SEARCH                                     │
│     ┌──────────────┐ ┌──────────────┐ ┌──────────────┐  │
│     │  npm / PyPI  │ │  MCP Tools   │ │  GitHub/Web  │  │
│     └──────────────┘ └──────────────┘ └──────────────┘  │
│     ┌─────────────────────────────┐ ┌────────────────┐  │
│     │ seek_symbol (AST symbols)   │ │ Episodic RAG   │  │
│     └─────────────────────────────┘ └────────────────┘  │
├─────────────────────────────────────────────────────────┤
│  3. EVALUATE                                            │
│     Score candidates (functionality, maintenance,       │
│     community, docs, license, deps)                     │
├─────────────────────────────────────────────────────────┤
│  4. DECIDE                                              │
│     ┌─────────┐  ┌──────────┐  ┌─────────┐  ┌────────┐  │
│     │  Adopt  │  │  Extend  │  │ Compose │  │ Build  │  │
│     │ as-is   │  │  /Wrap   │  │         │  │ Custom │  │
│     └─────────┘  └──────────┘  └─────────┘  └────────┘  │
├─────────────────────────────────────────────────────────┤
│  5. IMPLEMENT                                           │
│     Install package / Configure MCP /                   │
│     Write minimal custom code                           │
└─────────────────────────────────────────────────────────┘
```

---

## Decision Matrix

| Signal | Action |
|--------|--------|
| Exact match, well-maintained, MIT/Apache | **Adopt** - install and use directly |
| Partial match, solid foundation | **Extend** - install + write thin wrapper |
| Multiple focused matches | **Compose** - combine 2-3 focused packages |
| Nothing suitable found | **Build** - write custom, but informed by research |

---

## How to Use

### Step 0: Tool Availability Preflight

This is agent guidance, not an executable setup script. Check only the channels relevant to the task in front of you:

| Channel | Check | If missing |
|---------|-------|------------|
| Local Codebase Symbols | `seek_symbol(symbol_name="...")` | Fall back to inspect module `__all__` |
| Persistent Memory / RAG | `search_knowledge_and_memory(query="...")` | Proceed without episodic context |
| Package registry | `npm --version`, `uv pip --version` | Use web/docs search; avoid claiming registry coverage |
| GitHub CLI | `gh auth status` | Use public web or local git history |
| MCP Tools | Registered server tool schema list | Fall back to official docs or web search |

### Quick Mode (Inline)

Before writing a utility or adding functionality, mentally run through:

0. **Does this already exist in the repo?**  
   Locate existing declarations via `seek_symbol(symbol_name="...")` or search episodic memory via `search_knowledge_and_memory(query="...")` (do NOT run unbounded ripgrep scans).
1. **Is this a standard ecosystem problem?**  
   Check npm / PyPI (`uv add ...`, `npm install ...`).
2. **Is there an MCP tool for this?**  
   Check active MCP server schemas.
3. **Is there a skill for this?**  
   Check available skills catalog.
4. **Is there an established GitHub implementation or reference?**  
   Inspect maintained OSS implementations before creating net-new code.

### Full Mode (Subagent Researcher)

For non-trivial functionality or complex dependencies, dispatch the researcher subagent:

```python
invoke_subagent(
    subagent_type="kortext-researcher",
    prompt="""
    Research existing tools and packages for: [DESCRIPTION]
    Language / Framework: [LANG / STACK]
    Constraints: [LICENSE / PERFORMANCE CONSTRAINTS]

    Search: PyPI/npm, GitHub, MCP tools, and Kortext episodic memory.
    Return: Structured comparison table with explicit Adopt/Extend/Compose/Build recommendation.
    """
)
```

---

## Search Shortcuts by Category

### Development Tooling
- Linting & Formatting → `ruff`, `black`, `eslint`, `prettier`
- Testing → `pytest`, `vitest`, `playwright`
- Pre-commit & Git Hooks → `pre-commit`, `husky`, `lint-staged`

### AI & Agent Integration
- MCP Servers → Check FastMCP implementations first
- Prompt & Memory Management → Context7, Kortext episodic memory
- Document & Data Extraction → `unstructured`, `pdfplumber`, `pypdf`

### Data & APIs
- HTTP Clients → `httpx` (Python), `undici` / `ky` (Node)
- Validation → `pydantic` (Python), `zod` (TypeScript)
- Graph & Vector Stores → `falkordb`, `qdrant-client`

### Content & Publishing
- Markdown Processing → `mistune`, `markdown-it`, `unified`
- Image Optimization → `pillow`, `sharp`

---

## Integration Points

### With Planner / Task Orchestrator
The planner invokes research before decomposing implementation tasks:
- Identifies existing utilities and pre-built libraries
- Incorporates findings into the Task DAG (`manage_tasks`)
- Avoids authoring redundant bespoke code

### With Kortext Architect
The architect checks prior episodic decisions before changing subsystem contracts:
```python
search_knowledge_and_memory(
    query="prior evaluations of caching libraries or vector models",
    collection="kortext"
)
```

---

## Examples

### Example 1: "Add dead link checking"
```
Need: Check markdown files for broken URLs
Search: npm "markdown dead link checker", PyPI "markdown link check"
Found: textlint-rule-no-dead-link / markdown-link-check
Action: ADOPT - npm install markdown-link-check
Result: Zero custom code; robust, battle-tested validation
```

### Example 2: "Add HTTP client with retry and jitter"
```
Need: Resilient HTTP client with backoff retry
Search: PyPI "httpx retry"
Found: httpx with custom Transport or tenacity / backoff
Action: ADOPT + EXTEND - use httpx with tenacity retry decorator
Result: Minimal custom wrapper, production-proven HTTP foundation
```

### Example 3: "Add AST symbol navigation"
```
Need: Deterministic jump-to-declaration for code entities
Search: Local Kortext MCP tools
Found: seek_symbol (FalkorDB / Tree-sitter AST index)
Action: ADOPT - call seek_symbol directly instead of running regex grep
Result: Instant O(1) declaration lookup with zero token bleed
```

---

## Anti-Patterns

- **Jumping to Code:** Authoring a utility without checking if the codebase or ecosystem already provides it.
- **Ignoring MCP Tools:** Writing custom API scrapers when an MCP server tool is already connected.
- **Silent Skipping:** Reporting "nothing found" when a search channel was simply offline.
- **Over-Customizing:** Wrapping a library so heavily that it loses updates, documentation, and maintainability.
- **Dependency Bloat:** Installing a heavy multi-megabyte package for a 5-line utility.
