"""
Kortext FastMCP Server: Main integration point for AI agents and Knowledge OS.
Exposes seven tools to Antigravity CLI agents via stdio transport:

  1. search_knowledge_and_memory: federated multi-tier memory and codebase retrieval (read)
  2. record_system_outcome: persist directly to FalkorDB KG and journal (write)
  3. trigger_dream_mode: on-demand synaptic pruning and community detection (write)
  4. index_directory: on-demand Qdrant ingest (write)
  5. check_kortext_health: service health dashboard (read)
  6. delete_or_supersede_fact: KG fact management (write)
  7. trace_symbol_impact: blast radius and impact analysis (read)
"""
import asyncio
import json
import logging
import os
import re
import signal
import sys

def _sig_handler(signum, frame):
    os._exit(0)

try:
    signal.signal(signal.SIGTERM, _sig_handler)
    signal.signal(signal.SIGINT, _sig_handler)
except Exception:
    pass

from contextlib import asynccontextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Union

from dotenv import load_dotenv
from fastmcp import FastMCP

logger = logging.getLogger("kortext.server")

from kortext.retrieval import (
    RetrievalEngine,
    discover_vector_collections,
    resolve_workspace_root_for_collection,
)
from kortext.episodic import AgentNativeEpisodicDriver, VALID_CATEGORIES
from kortext.handoff import HandoffManager
from kortext.ingest import ingest as _ingest
from kortext.symbols.graph import SymbolGraphManager
from kortext.trust.sanitizer import CausalSanitizer, SecurityViolation

# Deterministically load .env from KORTEXT_ROOT regardless of caller's CWD
KORTEXT_ROOT = Path(__file__).resolve().parent.parent
CEREBRUM_ROOT = KORTEXT_ROOT
KORTEXT_ENV_PATH = KORTEXT_ROOT / ".env"
if KORTEXT_ENV_PATH.is_file():
    load_dotenv(KORTEXT_ENV_PATH)
load_dotenv()

# ── Singletons (shared across tool calls) ──────────────────────────────────

retrieval    = RetrievalEngine()
episodic     = AgentNativeEpisodicDriver()
symbol_graph = SymbolGraphManager()

JOURNAL_DIR = Path(os.getenv("JOURNAL_DIR", str(KORTEXT_ROOT / "journal")))
JOURNAL_DIR.mkdir(parents=True, exist_ok=True)
HANDOFFS_DIR = JOURNAL_DIR / "handoffs"
HANDOFFS_DIR.mkdir(parents=True, exist_ok=True)

CATEGORY_DIRS: Dict[str, str] = {
    "decision": "decisions",
    "roadmap": "roadmaps",
    "implementation": "implementations",
    "experiment": "experiments",
    "benchmark": "benchmarks",
    "investigation": "investigations",
    "research": "research",
    "report": "reports",
}



@asynccontextmanager
async def lifespan(app):
    try:
        signal.signal(signal.SIGTERM, _sig_handler)
        signal.signal(signal.SIGINT, _sig_handler)
    except Exception:
        pass

    try:
        await retrieval.initialize()
        if hasattr(episodic, "initialize"):
            await episodic.initialize()
        yield
    finally:
        # Re-install OS-level signal handler so any SIGTERM received during or
        # after loop teardown exits immediately with code 0 instead of resetting
        # to SIG_DFL (which causes Go cmd.Wait() to receive 'signal: terminated').
        try:
            signal.signal(signal.SIGTERM, lambda s, f: os._exit(0))
            signal.signal(signal.SIGINT, lambda s, f: os._exit(0))
        except Exception:
            pass

        try:
            await episodic.close()
        except Exception:
            pass

        try:
            if hasattr(retrieval, "close"):
                await retrieval.close()
        except Exception:
            pass



mcp = FastMCP(
    name="kortext",
    instructions=(
        "Kortext Knowledge OS is your grounded memory, code intelligence, and retrieval base with four knowledge tiers: "
        "(0) AST Symbols & Backlinks, (1) Operational Facts & Decisions, (2) Viking Code Structure, (3) Qdrant Vectors. "
        "ALWAYS call search_knowledge_and_memory before writing code or making architectural decisions. "
        "ALWAYS call trace_symbol_impact before refactoring functions, classes, or interfaces. "
        "ALWAYS call record_system_outcome after completing significant work or configuration changes."
    ),
    lifespan=lifespan,
)


# ── Tool 1: Retrieve ───────────────────────────────────────────────────────

@mcp.tool(
    description=(
        "Unified hybrid search across codebase knowledge, architecture outlines, episodic outcomes, "
        "and AST symbols. Queries all memory tiers in parallel and returns structured Markdown context "
        "respecting the token budget and detail level."
    )
)
async def search_knowledge_and_memory(
    query: str,
    collection: Optional[str] = None,
    workspace_root: Optional[str] = None,
    token_budget: int = 1500,
    detail_level: str = "balanced",
    project: Optional[str] = None,
) -> str:
    """
    Args:
        query:          The coding task, architectural question, or query to retrieve context for.
        collection:     Optional Qdrant collection name to search within (defaults to 'kortext_codebase', or 'all' for federation).
        workspace_root: Optional workspace path to scope hierarchical structure to.
        token_budget:   Maximum total estimated tokens across all memory tiers (default: 1500).
        detail_level:   Context detail level: 'compact', 'balanced', or 'comprehensive'.
        project:        Optional project scope, e.g. 'kortext', 'my_app', or 'all' to query across all projects. Defaults to active workspace/project.
    Returns:
        Structured JSON envelope with 4 in-budget memory tiers (Tier 0: symbolic_context,
        Tier 1: code_chunks, Tier 2: episodic_history, Tier 3: architectural_overview),
        total_estimated_tokens, and clean human/agent-readable markdown formatting.
    """
    if not workspace_root and collection:
        workspace_root = await resolve_workspace_root_for_collection(collection)

    res = await retrieval.federated_query(
        query=query,
        token_budget=token_budget,
        collection=collection,
        workspace_root=workspace_root,
        detail_level=detail_level,
        project=project,
    )

    # Format clean Markdown view
    md_lines = [
        f"## Federated Memory Retrieval: {query}",
        f"**Estimated Tokens:** {res.get('total_estimated_tokens', 0)} / {token_budget}\n",
    ]

    # Tier 0: AST Symbol Seek
    sym_ctx = res.get("symbolic_context", [])
    md_lines.append("### Tier 0: AST Symbol Declarations")
    if sym_ctx:
        for item in sym_ctx:
            if isinstance(item, dict):
                s_name = item.get("symbol") or item.get("name", "Unknown")
                kind = item.get("kind", "symbol")
                f_path = item.get("file") or item.get("file_path", "")
                sig = item.get("signature", "")
                lines = item.get("lines", [])
                line_str = f":{lines[0]}" if lines else ""
                md_lines.append(f"- **`{s_name}`** ({kind}) at `{f_path}{line_str}`")
                if sig:
                    md_lines.append(f"  - Signature: `{sig}`")
            else:
                md_lines.append(f"- {item}")
    else:
        md_lines.append("_No candidate symbol declarations located._")
    md_lines.append("")

    # Tier 1: Hybrid Codebase Chunks
    code_chunks = res.get("code_chunks", [])
    md_lines.append("### Tier 1: Hybrid Codebase Chunks")
    if code_chunks:
        for i, chunk in enumerate(code_chunks, 1):
            md_lines.append(f"#### Reference {i}\n```\n{chunk}\n```")
    else:
        md_lines.append("_No relevant codebase chunks retrieved._")
    md_lines.append("")

    # Tier 2: Episodic History
    episodic_history = res.get("episodic_history", [])
    md_lines.append("### Tier 2: Episodic History & Decisions")
    if episodic_history:
        for fact in episodic_history:
            md_lines.append(f"- {fact}")
    else:
        md_lines.append("_No historical episodic facts found._")
    md_lines.append("")

    # Tier 3: System Architecture Overview
    arch_overview = res.get("architectural_overview")
    if arch_overview:
        md_lines.append("### Tier 3: System Architecture Overview")
        md_lines.append(arch_overview)
        md_lines.append("")

    formatted_md = "\n".join(md_lines)

    res_copy = dict(res)
    res_copy["markdown"] = formatted_md
    return json.dumps(res_copy, indent=2)


# ── Tool 2: Record ─────────────────────────────────────────────────────────

@mcp.tool(
    description=(
        "Record a significant technical decision, configuration change, or work outcome. "
        "Persists to: (1) FalkorDB episodic knowledge graph directly without intermediate LLM proxy, "
        "and (2) a dated Markdown journal file for human-readable audit trail. Old conflicting facts "
        "are superseded, not deleted. Can accept structured entities/facts directly or raw narrative. "
        "CALL THIS after: changing env vars / ports / dependencies, choosing an architecture, "
        "fixing a non-trivial bug, or completing any substantial task."
    )
)
async def record_system_outcome(
    episode_name: str,
    content: str,
    category: str = "implementation",
    tags: Optional[list[str]] = None,
    project: Optional[str] = None,
    entities: Optional[list[dict[str, str]]] = None,
    facts: Optional[list[dict[str, str]]] = None,
    supersedes: Optional[list[str]] = None,
    trust_level: str = "speculative",
) -> str:
    """
    Args:
        episode_name: Short title (5-10 words), e.g. 'Switched embed server to port 8001'
        content:      Full description of the outcome, decision, or change.
        category:     Mandatory category: 'decision', 'roadmap', 'implementation', 'experiment', 'benchmark', 'investigation', 'research', 'report'
        tags:         Optional list of lowercase keyword tags, e.g. ['embedding', 'ports']
        project:      Optional project label, e.g. 'kortext' or 'big-je'
        entities:     Optional structured entities [{'name': '...', 'type': '...', 'summary': '...'}]
        facts:        Optional structured facts [{'source': '...', 'relation': '...', 'target': '...', 'fact': '...'}]
        supersedes:   Optional list of patterns/facts superseded by this outcome
        trust_level:  Trust anchor level: 'speculative' (0.50), 'tool_confirmed' (0.60), or 'user_approved' (1.00)
    Returns:
        Confirmation with paths to KG and journal.
    """
    if not isinstance(category, str) or category.lower().strip() not in VALID_CATEGORIES:
        raise ValueError(f"Invalid category '{category}'. Must be one of: {VALID_CATEGORIES}")
    cat = category.lower().strip()

    full_content = content
    if project:
        full_content = f"[Project: {project}]\n\n{content}"

    # MINJA Adversarial Causal Sanitizer Gate
    sanitizer = CausalSanitizer()
    if trust_level == "user_approved":
        source_tier = 1
    elif trust_level == "tool_confirmed":
        source_tier = 2
    else:
        source_tier = 3
    try:
        sanitizer.sanitize(
            subject=episode_name,
            relation="RECORDED",
            fact=full_content,
            source_tier=source_tier,
        )
    except SecurityViolation as sv:
        return f"🚨 BLOCKED BY MINJA CAUSAL SANITIZER: {sv}. Write operation rejected and quarantined."

    safe_title = re.sub(r"[^\w\-]+", "_", episode_name.strip().lower()).strip("_") or "outcome"
    today = datetime.now().strftime("%Y-%m-%d")
    now_time = datetime.now().strftime("%H:%M")

    # Category folder and dedicated outcome markdown file
    cat_dir_name = CATEGORY_DIRS[cat]
    category_dir = JOURNAL_DIR / cat_dir_name
    outcome_file = category_dir / f"{today}_{safe_title}.md"

    outcome_lines = [
        f"# {episode_name}\n",
        f"- **Date:** {today} {now_time}",
        f"- **Category:** {cat}",
        f"- **Project:** {project or 'kortext'}",
        f"- **Trust Level:** {trust_level}",
    ]
    if tags:
        outcome_lines.append(f"- **Tags:** {', '.join(tags)}")
    if supersedes:
        outcome_lines.append(f"- **Supersedes:** {', '.join(supersedes)}")
    outcome_lines.extend(["\n## Outcome Description\n", full_content, "\n"])
    outcome_content = "\n".join(outcome_lines)

    # Append to daily Markdown journal first (so data is never lost)
    journal_file = JOURNAL_DIR / f"{today}.md"
    entry_lines = [f"\n## {now_time} - {episode_name}\n", full_content]
    entry_lines.append(f"\n**Category:** {cat}")
    if tags:
        entry_lines.append(f"\n**Tags:** {', '.join(tags)}")
    if project:
        entry_lines.append(f"\n**Project:** {project}")
    if supersedes:
        entry_lines.append(f"\n**Supersedes:** {', '.join(supersedes)}")
    if trust_level:
        entry_lines.append(f"\n**Trust Level:** {trust_level}")
    entry_lines.append("\n")

    def _write_journal():
        category_dir.mkdir(parents=True, exist_ok=True)
        with open(outcome_file, "w") as f:
            f.write(outcome_content)
        with open(journal_file, "a") as f:
            f.write("\n".join(entry_lines))

    await asyncio.to_thread(_write_journal)

    # Persist to FalkorDB KG directly (fast, agent-native, no middle proxy daemon)
    kg_status = "✅ FalkorDB Episodic Memory"
    try:
        res = await episodic.record_outcome(
            episode_name=episode_name,
            content=full_content,
            tags=tags,
            project=project,
            entities=entities,
            facts=facts,
            supersedes=supersedes,
            trust_level=trust_level,
            category=cat,
        )
        kg_status = f"✅ FalkorDB KG ({res.get('entities_written', 0)} entities, {res.get('facts_written', 0)} facts, {res.get('superseded_count', 0)} superseded, trust: {res.get('trust_level', 'speculative')} [{res.get('trust_score', 0.5)}])"
    except Exception as e:
        kg_status = f"⚠️ FalkorDB KG skipped ({type(e).__name__}: {e})"

    return (
        f"✅ Recorded: '{episode_name}'\n"
        f"   → Category: {outcome_file}\n"
        f"   → Journal: {journal_file}\n"
        f"   → {kg_status}"
    )


# ── Tool 3: Dream Mode ─────────────────────────────────────────────────────

@mcp.tool(
    description=(
        "Trigger an on-demand Kortext Dream Mode consolidation cycle. Executes: "
        "(1) Synaptic pruning & stale fact contradiction resolution, archiving invalid facts to disk, "
        "(2) Graph community detection (Louvain algorithm) clustering code symbols into subsystems, "
        "(3) Abstract invariant induction across codebase decisions, and "
        "(4) Generates a dated dream report in journal/dreams/."
    )
)
async def trigger_dream_mode(
    project: str = "kortext",
    purge_stale: bool = False,
    invariants: Optional[list[dict[str, str]]] = None,
    stale_fact_names: Optional[list[str]] = None,
) -> str:
    """
    Args:
        project:          Target project label (default: 'kortext').
        purge_stale:      If True, physically removes superseded facts after archiving. Default False (soft-prune).
        invariants:       Optional list of newly induced architectural invariants: [{'domain': '...', 'rule': '...', 'rationale': '...'}].
        stale_fact_names: Optional list of older fact names to supersede during pruning.
    Returns:
        Structured summary of the dream consolidation report.
    """
    from kortext.dream import KortextDreamEngine
    engine = KortextDreamEngine()
    report = await engine.dream(
        project=project,
        purge_stale=purge_stale,
        invariants=invariants,
        stale_fact_names=stale_fact_names,
    )
    return (
        f"🌙 Dream Mode completed for project '{project}':\n"
        f"- Active Facts Remaining: {report['pruned_facts']['active_facts_remaining']}\n"
        f"- Superseded Facts Pruned: {report['pruned_facts']['superseded_facts_pruned']}\n"
        f"- Contradictions Flagged: {len(report['pruned_facts']['contradictions_flagged'])}\n"
        f"- Subsystem Clusters Found: {report['subsystem_clusters']}\n"
        f"- Invariants Active: {report['invariants_inducted']}\n"
        f"- Dream Report Written: {report['dream_report_path']}\n"
        f"- Invariants Log: {report['invariants_path']}"
    )


# ── Tool 4: Index ──────────────────────────────────────────────────────────

@mcp.tool(
    description=(
        "Index a directory into the Qdrant vector store so its files become "
        "retrievable by search_knowledge_and_memory. Uses upsert semantics: "
        "existing vectors are updated, not destroyed. Safe to run multiple times. "
        "Use this when adding a new project or re-indexing after major refactors."
    )
)
async def index_directory(
    path: str,
    collection: Optional[str] = None,
    symbols_graph: Optional[str] = None,
    exclude_patterns: Optional[list[str]] = None,
    auto_dream: bool = True,
) -> str:
    """
    Args:
        path:             Absolute path to the directory to index.
        collection:       Optional Qdrant collection name (defaults to 'kortext_codebase').
        symbols_graph:    Optional FalkorDB symbol graph name (defaults to '<collection>_symbols').
        exclude_patterns: Additional glob patterns to exclude (e.g. ['tests/', '*.spec.ts']).
        auto_dream:       Whether to automatically consolidate memory via DreamEngine after ingest (default True).
    Returns:
        Confirmation with document count.
    """
    if not Path(path).exists():
        return f"❌ Path does not exist: {path}"
    target_col = collection or os.getenv("KORTEXT_COLLECTION", os.getenv("QDRANT_COLLECTION", "kortext_codebase"))
    default_sym = os.getenv("KORTEXT_SYMBOLS_GRAPH", os.getenv("FALKORDB_SYMBOLS_GRAPH", "kortext_symbols"))
    target_sym = symbols_graph or (f"{target_col}_symbols" if target_col not in ("kortext_codebase", "cerebrum_codebase") else default_sym)

    async def _run_indexing():
        await _ingest(path, extra_excludes=exclude_patterns or [], collection=target_col, symbols_graph=target_sym)
        if auto_dream:
            from kortext.dream import DreamEngine
            await DreamEngine().dream(project=target_col)

    asyncio.create_task(_run_indexing())
    return f"🚀 Indexing started in background for '{path}' into Qdrant collection '{target_col}' and FalkorDB graph '{target_sym}'."


# ── Tool 4b: List Collections ───────────────────────────────────────────────

@mcp.tool(
    description=(
        "List all available Qdrant vector collections with their point counts and indexing status. "
        "Call this to discover active knowledge collections (e.g. 'kortext_codebase', 'Antigravity_Docs') "
        "before querying search_knowledge_and_memory with the 'collection' argument."
    )
)
async def list_vector_collections() -> Dict[str, Any]:
    """
    Returns a dictionary of collections, point counts, vector configurations, and total collections.
    """
    qdrant_url_env = os.getenv("QDRANT_URL")
    if not qdrant_url_env or not qdrant_url_env.strip():
        # Embedded mode discovery: directly inspect embedded storage via unified discovery
        try:
            collections_data = await asyncio.to_thread(discover_vector_collections)
            return {
                "status": "embedded",
                "collections": collections_data,
                "total_collections": len(collections_data),
            }
        except Exception as e:
            return {
                "status": "embedded",
                "error": str(e),
                "collections": [],
                "total_collections": 0,
            }

    import httpx
    qdrant_url = qdrant_url_env.strip().replace("://localhost", "://127.0.0.1").rstrip("/")
    collections_data = []

    try:
        async with httpx.AsyncClient(timeout=4.0) as client:
            resp = await client.get(f"{qdrant_url}/collections")
            if resp.status_code == 200:
                raw_cols = resp.json().get("result", {}).get("collections", [])

                async def _get_info(col_dict: dict):
                    c_name = col_dict.get("name")
                    try:
                        info_resp = await client.get(f"{qdrant_url}/collections/{c_name}")
                        if info_resp.status_code == 200:
                            res = info_resp.json().get("result", {})
                            points_count = res.get("points_count", 0)
                            indexed_vectors = res.get("indexed_vectors_count", points_count)
                            status_str = res.get("status", "green")
                            return {
                                "name": c_name,
                                "points_count": points_count,
                                "indexed_vectors_count": indexed_vectors,
                                "status": status_str,
                            }
                    except Exception:
                        pass
                    return {"name": c_name, "points_count": "unknown"}

                collections_data = await asyncio.gather(*[_get_info(c) for c in raw_cols])
                return {
                    "status": "ok",
                    "collections": list(collections_data),
                    "total_collections": len(collections_data),
                }
    except Exception as e:
        logger.warning(f"Could not list collections via HTTP: {e}")

    # Fallback via async Qdrant client
    client = None
    try:
        from qdrant_client import AsyncQdrantClient
        client = AsyncQdrantClient(url=qdrant_url)
        cols = await client.get_collections()

        async def _client_info(c):
            try:
                info = await client.get_collection(c.name)
                return {
                    "name": c.name,
                    "points_count": info.points_count,
                    "status": str(info.status),
                }
            except Exception:
                return {"name": c.name, "points_count": "unknown"}

        collections_data = await asyncio.gather(*[_client_info(c) for c in cols.collections])
        return {
            "status": "ok",
            "collections": list(collections_data),
            "total_collections": len(collections_data),
        }
    except Exception as e:
        return {"status": "error", "message": f"Failed to list collections: {e}", "collections": []}
    finally:
        if client:
            try:
                await client.close()
            except Exception:
                pass


# ── Tool 5: Health ─────────────────────────────────────────────────────────

@mcp.tool(
    description=(
        "Check the health of all Kortext backend services. Returns a JSON status "
        "report for Qdrant, FalkorDB, the inference server (embeddings/reranker), and the dashboard. "
        "Call this if other Kortext tools return errors or time out."
    )
)
async def check_kortext_health() -> str:
    """Returns JSON with status of each service."""
    from kortext.health import audit_kortext_health

    report = await audit_kortext_health(include_browser_ui=False, include_invariants=True)
    return json.dumps(report, indent=2)


@mcp.tool(
    name="check_cerebrum_health",
    description="Legacy alias for check_kortext_health.",
)
async def check_cerebrum_health() -> str:
    """Returns JSON with status of each service (legacy alias)."""
    return await check_kortext_health()


# ── Tool 6: Delete / Supersede ─────────────────────────────────────────────

@mcp.tool(
    description=(
        "Mark a specific Graphiti fact as superseded (soft-delete). Use when a previously "
        "recorded fact is no longer valid, such as when a port changed, a dependency was removed, "
        "or a past decision was reversed. The fact is marked invalid with your reason, "
        "preserving audit history. Requires the fact episode name or ID from a prior search."
    )
)
async def delete_or_supersede_fact(fact_id: str, reason: str) -> str:
    """
    Args:
        fact_id: The episode name or ID of the fact to supersede.
        reason:  Why this fact is no longer valid.
    Returns:
        Confirmation message.
    """
    await episodic.delete_fact(fact_id, reason)
    return f"✅ Fact '{fact_id}' marked as superseded.\nReason recorded: {reason}"


# ── Tool 7: Blast-Radius / Impact Analysis ─────────────────────────────────

@mcp.tool(
    description=(
        "Trace the upstream callers or downstream dependencies of a symbol across the codebase. "
        "Performs fast graph path traversal in FalkorDB over REFERENCES, IMPORTS, CALLS, and "
        "IMPLEMENTS edges with adaptive token budgeting (L1 signatures for 1-hop, L0 for 2-hop, "
        "aggregated counts for transitive). CALL THIS before refactoring or deleting a symbol."
    )
)
async def trace_symbol_impact(
    symbol: str,
    direction: str = "upstream",
    max_depth: int = 3,
    symbols_graph: Optional[str] = None,
    token_budget: Optional[int] = 1500,
) -> str:
    """
    Args:
        symbol:        Name of the function, class, method, or struct to analyze.
        direction:     'upstream' (dependents/callers who will break) or 'downstream' (callees/dependencies).
        max_depth:     Graph search depth hops (1 to 5, default: 3).
        symbols_graph: Optional FalkorDB graph name (defaults to 'kortext_symbols').
        token_budget:  Optional max tokens for the response (default: 1500).
    Returns:
        Structured JSON report showing all impacted files, lines, relationships, and progressive summary.
    """
    def _do_trace() -> str:
        target_graph = symbols_graph or os.getenv("KORTEXT_SYMBOLS_GRAPH", os.getenv("FALKORDB_SYMBOLS_GRAPH", "kortext_symbols"))
        mgr = symbol_graph if target_graph == symbol_graph.graph_name else SymbolGraphManager(graph_name=target_graph)
        impact = mgr.trace_symbol_impact(symbol, direction=direction, max_depth=max_depth, token_budget=token_budget)
        return json.dumps(impact, indent=2)

    return await asyncio.to_thread(_do_trace)


# ── Tool 8: Anti-Ripgrep Deterministic Symbol Seek ───────────────────────

@mcp.tool(
    description=(
        "Deterministic symbol locator replacing brute-force ripgrep loops. "
        "Looks up exact symbol declaration, signature, docstring, callers, and callees "
        "directly from the compiler AST knowledge graph in FalkorDB in <2ms, consuming <150 tokens."
    )
)
async def seek_symbol(
    symbol_name: str,
    detail_level: str = "skeleton",
    file_hint: Optional[str] = None,
) -> str:
    """
    Args:
        symbol_name: Name or qualified name of the symbol (function, class, struct, method).
        detail_level: Progressive detail level: 'skeleton' (signature, docstring, types, stubbed body),
                      'interface' (skeleton + callers, callees, methods), or 'full' (complete implementation).
        file_hint: Optional filename or path substring to disambiguate identical symbols.
    Returns:
        Structured JSON declaration and immediate call graph.
    """
    def _do_seek() -> str:
        from kortext.symbols.seek import SymbolSeekEngine
        seeker = SymbolSeekEngine()
        if detail_level != "skeleton":
            return seeker.seek_symbol(symbol_name, detail_level=detail_level, file_hint=file_hint)
        return seeker.seek_symbol(symbol_name, file_hint=file_hint)

    return await asyncio.to_thread(_do_seek)


# ── Tool 9: Task DAG Project Management Engine ───────────────────────────

@mcp.tool(
    description=(
        "Graph-backed Task DAG state machine for multi-agent project decomposition. "
        "Allows creating tasks, declaring strict dependencies, querying ready leaf tasks "
        "for subagent delegation, and recording execution state."
    )
)
async def manage_tasks(
    action: str = "get_ready",
    title: Optional[str] = None,
    description: Optional[str] = None,
    complexity: int = 1,
    assigned_to: str = "primary",
    depends_on: Optional[list[str]] = None,
    task_id: Optional[str] = None,
    status: Optional[str] = None,
    error: Optional[str] = None,
    project_id: Optional[str] = None,
    episode_name: Optional[str] = None,
) -> str:
    """
    Args:
        action: 'create', 'get_ready', 'update_status', or 'list_all'.
        title: Task title for 'create'.
        description: Task requirements and verification criteria for 'create'.
        complexity: Estimated complexity score 1-10.
        assigned_to: Target subagent persona (e.g. 'kortext-task-runner').
        depends_on: List of upstream prerequisite task IDs.
        task_id: Target task ID for 'update_status'.
        status: New state ('pending', 'ready', 'in_progress', 'completed', 'failed').
        error: Failure explanation if status is 'failed'.
        project_id: Optional project ID, e.g. 'kortext', 'my_app', or 'all'. Defaults to 'kortext' if unspecified.
        episode_name: Optional episode name to link the completed task to via (:Task)-[:PRODUCED_OUTCOME]->(:Episodic).
    Returns:
        JSON response with task details, ready tasks, or operation confirmation.
    """
    def _do_manage() -> str:
        from kortext.tasks.tracker import TaskDAGTracker
        tracker = TaskDAGTracker()
        act = action.lower().strip()

        if act == "create":
            if not title:
                return json.dumps({"error": "Missing 'title' for task creation"})
            tid = tracker.create_task(
                title=title,
                description=description or "",
                complexity=complexity,
                assigned_to=assigned_to,
                depends_on=depends_on,
                project_id=project_id,
            )
            return json.dumps({"status": "created", "task_id": tid})

        elif act in ("get_ready", "ready"):
            ready = tracker.get_ready_tasks(project_id=project_id)
            return json.dumps({"ready_tasks": ready}, indent=2)

        elif act in ("list_all", "list"):
            tasks = tracker.get_all_tasks(project_id=project_id)
            return json.dumps({"tasks": tasks}, indent=2)

        elif act == "update_status":
            if not task_id or not status:
                return json.dumps({"error": "Missing 'task_id' or 'status'"})
            ok = tracker.update_task_status(task_id, status=status, error=error)
            if episode_name and status == "completed":
                tracker.link_task_to_outcome(task_id, episode_name)
            return json.dumps({"task_id": task_id, "updated": ok, "status": status})

        return json.dumps({"error": f"Unknown action: {action}"})

    return await asyncio.to_thread(_do_manage)


# ── Tool 10: Cross-Agent Session Handoff Baton ────────────────────────────

@mcp.tool(
    description=(
        "Manage cross-agent context handoff batons across session and agent boundaries. "
        "Allows Antigravity, Claude Code, Codex, and peer subagents to exchange "
        "open hypotheses, unresolved questions, active blast radius, and current scope without context loss."
    )
)
async def memory_session_handoff(
    action: str = "create",
    target_agent: Optional[str] = None,
    current_scope: Optional[str] = None,
    open_hypotheses: Optional[list[str]] = None,
    unresolved_questions: Optional[list[str]] = None,
    active_blast_radius: Optional[list[str]] = None,
    baton_id: Optional[str] = None,
) -> str:
    """
    Args:
        action: 'create' to save a new handoff baton, 'read' to retrieve a baton,
                'list' to see pending handoffs, or 'complete' to mark a baton consumed.
        target_agent: Destination agent or role (e.g. 'claude-code', 'codex', 'subagent', 'antigravity').
        current_scope: Active task, file scope, or objective.
        open_hypotheses: Working hypotheses currently under investigation.
        unresolved_questions: Open questions or decisions needed from the next agent.
        active_blast_radius: List of modified or sensitive symbols/files.
        baton_id: Specific baton identifier (for read or complete).
    Returns:
        Structured handoff baton data or confirmation.
    """
    return await asyncio.to_thread(
        HandoffManager(HANDOFFS_DIR).execute,
        action=action,
        target_agent=target_agent,
        current_scope=current_scope,
        open_hypotheses=open_hypotheses,
        unresolved_questions=unresolved_questions,
        active_blast_radius=active_blast_radius,
        baton_id=baton_id,
    )


# ── Entry point ────────────────────────────────────────────────────────────

def main():
    import argparse
    parser = argparse.ArgumentParser(description="Kortext FastMCP Server")
    parser.add_argument("--transport", default=os.getenv("MCP_TRANSPORT", "stdio"), choices=["stdio", "sse"], help="MCP transport protocol (stdio or sse)")
    parser.add_argument("--port", type=int, default=int(os.getenv("MCP_PORT", os.getenv("KORTEXT_MCP_PORT", os.getenv("CEREBRUM_MCP_PORT", "8005")))), help="Port for SSE transport")
    parser.add_argument("--host", default=os.getenv("MCP_HOST", "127.0.0.1"), help="Host address for SSE transport")
    args, _ = parser.parse_known_args()

    def _sig_handler(signum, frame):
        os._exit(0)

    try:
        signal.signal(signal.SIGTERM, _sig_handler)
        signal.signal(signal.SIGINT, _sig_handler)
    except Exception:
        pass

    try:
        if args.transport == "sse":
            logger.info("[Kortext Server] Starting FastMCP on SSE transport at http://%s:%s", args.host, args.port)
            mcp.run(transport="sse", host=args.host, port=args.port)
        else:
            mcp.run(transport="stdio")
    except (KeyboardInterrupt, SystemExit):
        pass
    finally:
        # Crucial for stdio transport: once the MCP session ends (e.g. stdin EOF or client disconnect),
        # immediately terminate the process with exit code 0 via os._exit(0).
        # This prevents hanging during Python interpreter thread joins (e.g. onnxruntime/anyio workers)
        # which would cause Go MCP client's 5s timeout to elapse and trigger 'signal: terminated'.
        os._exit(0)


if __name__ == "__main__":
    main()
