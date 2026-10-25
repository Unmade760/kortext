---
name: expand-contract-refactor
description: Use when refactoring shared interfaces, renaming or moving core symbols across callers, auditing architecture and blast radius, or executing zero-downtime database, FalkorDB graph, or Qdrant vector migrations.
---

# Expand-Contract Refactoring, Architecture & Schema Migration Protocol

Unifies zero-downtime interface refactoring (`Expand -> Migrate -> Contract`), AST blast-radius architecture reviews (`kortext-architect`), and relational/graph/vector database migrations (`database-migrations`).

## 1. Stage 0: Architectural Blast-Radius Audit (`trace_symbol_impact`)

Before modifying any shared symbol, class, MCP tool, or schema, map its exact caller topology in FalkorDB (`<10ms`, zero `rg`):

```python
decl = seek_symbol(symbol_name="TargetSymbol", detail_level="skeleton")
upstream = trace_symbol_impact(symbol="TargetSymbol", direction="upstream", max_depth=3, token_budget=1500)
downstream = trace_symbol_impact(symbol="TargetSymbol", direction="downstream", max_depth=2)
```

| Blast Tier | Files / Callers Affected | Required Execution Strategy |
|---|---|---|
| **Tier 1: Isolated** | `1` file, `0` external callers | Direct atomic edit via `replace_file_content` + unit test (`single_agent`). |
| **Tier 2: Local** | `1–3` files, `1–5` callers | Coordinated inline update + targeted `pytest` run in a single commit. |
| **Tier 3: Subsystem** | `4–10` files, `6–20` callers ($C \ge 7$) | Decompose into Task DAG (`manage_tasks`) + 3-Phase **Expand-Contract** with backwards-compatible shim. |
| **Tier 4: Core / Schema** | `>10` files, `>20` callers, or persistent DB/Graph/Vector schema | Record ADR (`to-spec`) + 3-Phase **Expand-Contract** across batched commits + `trigger_dream_mode` community audit. |

## 2. The 3-Phase Expand-Contract Lifecycle

Never perform "big-bang" renames or breaking signature changes across $\ge 4$ files in a single commit. Keep CI 100% green at every step:

| Phase | Code / Interface Refactoring | Relational DB (Postgres/ORM) | FalkorDB Graph & Qdrant Vector Substrate |
|---|---|---|---|
| **1. EXPAND** | Introduce `new_symbol` with frozen typed contracts. Keep `old_symbol` alive as a thin deprecation shim forwarding to `new_symbol`. Write unit tests for `new_symbol`. | Add nullable column or column with default (`ALTER TABLE ... ADD COLUMN`). Create indexes non-blockingly (`CREATE INDEX CONCURRENTLY`). Dual-write to old and new. | **FalkorDB**: Create idempotent B-Tree index (`CREATE INDEX FOR (n:Label) ON (n.prop)`), dual-write new edge/property, read with `coalesce(n.new, n.old)`. **Qdrant**: Create payload index with `wait=False` or build new Blue-Green collection. |
| **2. MIGRATE** | Partition callers from `trace_symbol_impact` into cohesive batches of `3–5` files (leaf callers $\rightarrow$ domain modules $\rightarrow$ routes). Run `uv run pytest -q` and commit after each batch. | Backfill historical rows in bounded batches (`LIMIT 10000 FOR UPDATE SKIP LOCKED`) in a separate data migration (never mix DDL + large DML in one transaction). Switch reads to new column. | **FalkorDB**: Backfill node properties or copy edges in `LIMIT 1000` loops so the Redis single thread never blocks. **Qdrant**: Backfill vectors into new collection and atomically swap collection alias (`update_collection_aliases`). |
| **3. CONTRACT** | Re-run `trace_symbol_impact(symbol="old_symbol", direction="upstream")` and confirm `0` callers remain. Delete legacy shim, run full `pytest` + `ruff`, and persist via `record_system_outcome(category="refactor")`. | Remove old column references in app code, deploy, then drop legacy column (`ALTER TABLE ... DROP COLUMN`) in a forward migration. | **FalkorDB**: Delete legacy edges/properties in `LIMIT 1000` batches. Run `trigger_dream_mode(project="kortext")` to recompute Louvain community modularity and verify zero orphaned symbols. |

## 3. Architectural Hygiene & Anti-Patterns

| Anti-Pattern | Why It Fails | Mandated Protocol Action |
|---|---|---|
| **Big-Bang Rename across 20+ Files** | Breaks in-flight branches, hides regressions in noisy diffs, and fails mid-migration. | Use Phase 1 shim + Phase 2 batched caller migration (`3–5` files per commit). |
| **Premature Contraction** | Deleting `old_symbol` before checking `trace_symbol_impact` breaks dynamic/test callers. | Require `trace_symbol_impact` upstream caller count `== 0` before deleting the shim. |
| **`NOT NULL` Column Without Default** | Triggers full table rewrite and exclusive write lock in production. | Add nullable column $\rightarrow$ batched backfill $\rightarrow$ add constraint (`NOT VALID` then `VALIDATE`). |
| **Unbounded Cypher `MATCH (n) SET ...`** | Blocks FalkorDB/Redis event loop and spikes memory on large graphs. | Always paginate graph mutations with `WITH n LIMIT 1000`. |
| **Editing Deployed Migration Files** | Causes irreversible checksum and schema drift across environments. | Migrations are immutable once applied; always author a new forward migration. |

## 4. Deep-Module Architecture Survey (`detect_shallow_modules`)

When surveying a codebase for architectural deepening opportunities (John Ousterhout's *A Philosophy of Software Design*), run the bundled blast-radius classifier (`python3 ~/.gemini/config/plugins/kortext/skills/expand-contract-refactor/scripts/check_blast_radius.py <Symbol>`) or query `SubsystemClusterer.detect_shallow_modules()` to identify shallow pass-through modules ($\ge 3$ exported symbols averaging $\le 12$ lines each) and consolidate them behind a single deep facade.
