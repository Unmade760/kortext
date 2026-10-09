# Coding Standards and Guidelines

This document defines code quality, typing, architecture, and safety rules for the Kortext codebase.

---

## 1. Core Principles

### Immutability (CRITICAL)
Always create new objects; never mutate existing data structures in place:

```python
# Recommended: Immutable dataclass or new copy
from dataclasses import dataclass

@dataclass(frozen=True)
class SymbolRecord:
    name: str
    file_path: str
    line_number: int

# Updating state: produce a new instance
updated_record = SymbolRecord(
    name=record.name,
    file_path=record.file_path,
    line_number=new_line,
)

# Dictionary copying
updated_payload = {**original_payload, "status": "active"}
```

- Use `dataclasses.dataclass(frozen=True)` or Pydantic `ConfigDict(frozen=True)`.
- Use immutable tuples, `MappingProxyType`, or create fresh copies (`{**orig, "key": val}`).
- Never mutate incoming function parameters.
- **Rationale**: Immutable data structures eliminate hidden side effects, guarantee race-free concurrency, and keep unit testing deterministic.

### Deterministic AST Ground Truth Over Regex Sweeps
- Code definitions and compiler-grade ASTs (Tier 0) take precedence over vector embeddings (Tier 3) or heuristic text searches.
- **Anti-Ripgrep Rule**: Never use brute-force regex or text search sweeps to discover symbols. Always use deterministic Tree-sitter AST queries or `seek_symbol`.

### High Cohesion and Small Files
- **Many small files > few large files**:
  - Typical file size: **200-400 lines of code**.
  - Soft maintainability ceiling: **800 lines of code**.
  - When a module approaches 400 lines, extract cohesive helpers, parsers, or domain submodules.
  - Organize by feature and domain, not generic catch-all buckets.

### KISS, DRY, and YAGNI
- Prefer straightforward, readable implementations over premature abstractions.
- Extract common logic into focused utilities when repetition is proven.
- Avoid speculative features or unused generic wrappers.

---

## 2. Python Standards & Typing

### Formatting & Style
- Follow PEP 8 conventions.
- Line length: Keep lines under 100 characters where practical.
- Imports: Group logically into standard library, third-party libraries, and internal `kortext` packages. Sort alphabetically within groups.

### Strict Type Annotations
- Include type annotations on all function, method, and class definitions.
- Use standard Python typing syntax (`list[str]`, `dict[str, Any]`, `X | None`).
- Avoid unconstrained `Any`. Use dataclasses, Pydantic models, or `TypedDict` for structured payloads.

```python
# Recommended: Explicit typing
def trace_symbol_impact(
    symbol_name: str,
    direction: Literal["upstream", "downstream"] = "upstream",
    max_depth: int = 3,
) -> ImpactReport:
    ...
```

### Function Design & Nesting
- Keep functions concise (under 50 lines typical).
- Avoid deep nesting (>4 levels). Use early returns and guard clauses to flatten control flow.
- Extract complex multi-stage pipelines into descriptive private helpers.

---

## 3. Explicit Error Handling & Boundaries

### No Swallowed Exceptions
- Handle errors explicitly at every boundary; never allow unhandled errors to crash background daemons or FastMCP endpoints.
- **Strictly Prohibited**: `except Exception: pass`. If an exception is safely ignorable, log an explicit debug statement explaining the rationale.

```python
# Prohibited: Swallowing exceptions silently
try:
    sync_file(path)
except Exception:
    pass

# Recommended: Explicit handling and contextual logging
try:
    sync_file(path)
except FileNotFoundError as err:
    logger.debug("File %s deleted before sync completed: %s", path, err)
except ParseError as err:
    logger.warning("Syntax error in %s during incremental AST sync: %s", path, err)
```

### Safe Error Envelopes
- UI-facing and tool-result envelopes must return actionable, structured descriptions.
- Never leak sensitive internal stack traces, system paths, or credential fragments into agent-facing responses.

### Boundary Input Validation
- Validate all incoming API parameters, schemas, and tool arguments at system boundaries using Pydantic models or type guards.
- Fail fast with descriptive error messages when inputs violate specifications.

---

## 4. Substrate & Database Invariants

### FalkorDB (Symbol & Episodic Knowledge Graphs)
- **Mandatory Parameterized Queries**: Always use `$param` Cypher syntax to eliminate injection risks:

```python
# Recommended: Parameterized Cypher query
query = "MATCH (s:Symbol {name: $name}) RETURN s"
client.query(query, {"name": symbol_name})

# Prohibited: String formatting / interpolation
query = f"MATCH (s:Symbol {{name: '{symbol_name}'}}) RETURN s"
```

- **Bi-Temporal Preservation**: Never delete historical facts. Link newer revisions using `[:SUPERSEDES]` edges accompanied by validity timestamps.

### FastMCP Sole Custodian (Vector & Key-Value Stores)
- The FastMCP server daemon (`kortext.server`) is the single, exclusive custodian of vector stores (Qdrant) and RocksDB metadata.
- Subagents, background sidecars, and tools must never instantiate `QdrantClient(path=...)` directly in embedded mode.
- Direct embedded instantiation triggers SQLite/RocksDB advisory file locks (`LOCK_EX`), causing database lock errors and index corruption. All vector operations must route through FastMCP server tools.

---

## 5. Package Organization & Paths

### Package References
- Code must reside in and reference the `kortext` namespace:
  - `kortext.cli`: Command-line interface and daemon lifecycle management.
  - `kortext.server`: FastMCP server implementation and tool registrations.
  - `kortext.retrieval`: 5-signal hybrid search engine and HippoRAG associative walks.
  - `kortext.chunking`: Tree-sitter AST syntax parsers, skeleton extractors, and preambles.
  - `kortext.watcher`: Incremental file observation and hot-sync sidecar.
  - `kortext.dream`: Autonomous memory consolidation and Louvain clustering.
  - `kortext.dashboard`: Real-time telemetry and graph visualization application.

### Path Handling
- **No Hardcoded Machine Paths**: Never write paths such as `/Users/...` or `/home/...` into source code or test fixtures.
- Resolve repository and data paths dynamically relative to module files or standard directories:

```python
from pathlib import Path

KORTEXT_ROOT = Path(__file__).resolve().parent.parent
```

- Keep secrets in `.env` and document all required variables in `.env.example`.

---

## 6. Testing & Quality Assurance

1. **Mandatory TDD**: Write tests first (RED), implement minimal logic (GREEN), refactor cleanly (REFACTOR), and verify all suites (VERIFY).
2. **80%+ Coverage**: Maintain at least 80% line and branch test coverage.
3. **Substrate Isolation**: Tests must create isolated collections or graphs and clean up resources upon completion.
4. **Verification Commands**:
   - `uv run pytest -q`
   - `uv run pytest -q tests/test_code_hygiene.py`
   - `python3 scripts/test_plugin_manifest.py`
