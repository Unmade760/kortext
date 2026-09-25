"""
FastMCP server: main integration point for AI agents.
Exposes seven tools to Antigravity CLI agents via stdio transport:

  1. search_knowledge_and_memory: full LangGraph RAG pipeline (read)
  2. record_system_outcome: persist directly to FalkorDB KG and journal (write)
  3. trigger_dream_mode: on-demand synaptic pruning and community detection (write)
  4. index_directory: on-demand Qdrant ingest (write)
  5. check_cerebrum_health: service health dashboard (read)
  6. delete_or_supersede_fact: KG fact management (write)
  7. trace_symbol_impact: blast radius and impact analysis (read)
"""
import asyncio
import json
import os
import signal
import sys
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from dotenv import load_dotenv
from fastmcp import FastMCP

from cerebrum.graph import CerebrumState, make_graph
from cerebrum.retrieval import RetrievalEngine
from cerebrum.viking import VikingChunker
from cerebrum.episodic import AgentNativeEpisodicDriver
from cerebrum.ingest import ingest as _ingest
from cerebrum.symbols.graph import SymbolGraphManager
from cerebrum.trust.sanitizer import CausalSanitizer, SecurityViolation

# Deterministically load .env from CEREBRUM_ROOT regardless of caller's CWD
CEREBRUM_ROOT = Path(__file__).resolve().parent.parent
CEREBRUM_ENV_PATH = CEREBRUM_ROOT / ".env"
if CEREBRUM_ENV_PATH.is_file():
    load_dotenv(CEREBRUM_ENV_PATH)
load_dotenv()

# ── Singletons (shared across tool calls) ──────────────────────────────────

retrieval    = RetrievalEngine()
viking       = VikingChunker(workspace_root=os.getenv("WORKSPACE_ROOTS") or str(Path.home()))
episodic     = AgentNativeEpisodicDriver()
symbol_graph = SymbolGraphManager()
_graph       = None  # built after async init

JOURNAL_DIR = Path(os.getenv("JOURNAL_DIR", str(CEREBRUM_ROOT / "journal")))
JOURNAL_DIR.mkdir(parents=True, exist_ok=True)
HANDOFFS_DIR = JOURNAL_DIR / "handoffs"
HANDOFFS_DIR.mkdir(parents=True, exist_ok=True)


@asynccontextmanager
async def lifespan(app):
    global _graph
    try:
        loop = asyncio.get_running_loop()
        loop.add_signal_handler(signal.SIGTERM, lambda: os._exit(0))
        loop.add_signal_handler(signal.SIGINT, lambda: os._exit(0))
    except (NotImplementedError, RuntimeError):
        pass
    await retrieval.initialize()
    await episodic.initialize()
    _graph = make_graph(retrieval, viking, episodic, symbol_graph=symbol_graph)
    yield
    await episodic.close()


mcp = FastMCP(
    name="cerebrum",
    instructions=(
        "Cerebrum is your grounded memory, code intelligence, and retrieval base with four knowledge tiers: "
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
        "Query the Cerebrum RAG and unified memory pipeline. Returns a structured Markdown "
        "block with grounded context tiers: (0) Deterministic Symbol Declarations & Cross-File "
        "References from the FalkorDB symbol graph (exact definitions, imports, callers), "
        "(1) Operational Facts & Decisions from the temporal knowledge graph (Graphiti/FalkorDB), "
        "(2) System Architecture Overview from the Viking hierarchical code map, and "
        "(3) Ground-Truth Code References from Qdrant with Qwen3 cross-encoder reranking. "
        "CALL THIS before writing code, making architectural decisions, or answering "
        "questions about the local codebase structure."
    )
)
async def search_knowledge_and_memory(
    prompt: str,
    collection: Optional[str] = None,
    workspace_root: Optional[str] = None,
) -> str:
    """
    Args:
        prompt:         The coding task, architectural question, or query to retrieve context for.
        collection:     Optional Qdrant collection name to search within (defaults to 'cerebrum_codebase', or 'all' for federation).
        workspace_root: Optional workspace path to scope OpenViking hierarchical structure to.
    Returns:
        Structured Markdown with exact symbol references, operational decisions, and code snippets.
    """
    global _graph
    if _graph is None:
        await retrieval.initialize()
        await episodic.initialize()
        _graph = make_graph(retrieval, viking, episodic, symbol_graph=symbol_graph)

    state = CerebrumState(
        query=prompt,
        collection=collection,
        workspace_root=workspace_root,
        kg_facts=[],
        viking_summaries="",
        doc_snippets=[],
        symbol_results=[],
        final_context="",
    )
    result = await _graph.ainvoke(state)
    return result["final_context"]


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
        tags:         Optional list of lowercase keyword tags, e.g. ['embedding', 'ports']
        project:      Optional project label, e.g. 'cerebrum' or 'big-je'
        entities:     Optional structured entities [{'name': '...', 'type': '...', 'summary': '...'}]
        facts:        Optional structured facts [{'source': '...', 'relation': '...', 'target': '...', 'fact': '...'}]
        supersedes:   Optional list of patterns/facts superseded by this outcome
        trust_level:  Trust anchor level: 'speculative' (0.50), 'tool_confirmed' (0.60), or 'user_approved' (1.00)
    Returns:
        Confirmation with paths to KG and journal.
    """
    full_content = content
    if project:
        full_content = f"[Project: {project}]\n\n{content}"

    # MINJA Adversarial Causal Sanitizer Gate
    sanitizer = CausalSanitizer()
    source_tier = 1 if trust_level == "user_approved" else 2
    try:
        sanitizer.sanitize(
            subject=episode_name,
            relation="RECORDED",
            fact=full_content,
            source_tier=source_tier,
        )
    except SecurityViolation as sv:
        return f"🚨 BLOCKED BY MINJA CAUSAL SANITIZER: {sv}. Write operation rejected and quarantined."

    # Append to daily Markdown journal first (so data is never lost)
    today        = datetime.now().strftime("%Y-%m-%d")
    now_time     = datetime.now().strftime("%H:%M")
    journal_file = JOURNAL_DIR / f"{today}.md"
    entry_lines  = [f"\n## {now_time} - {episode_name}\n", full_content]
    if tags:
        entry_lines.append(f"\n**Tags:** {', '.join(tags)}")
    if project:
        entry_lines.append(f"\n**Project:** {project}")
    if supersedes:
        entry_lines.append(f"\n**Supersedes:** {', '.join(supersedes)}")
    if trust_level:
        entry_lines.append(f"\n**Trust Level:** {trust_level}")
    entry_lines.append("\n")

    with open(journal_file, "a") as f:
        f.write("\n".join(entry_lines))

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
        )
        kg_status = f"✅ FalkorDB KG ({res.get('entities_written', 0)} entities, {res.get('facts_written', 0)} facts, {res.get('superseded_count', 0)} superseded, trust: {res.get('trust_level', 'speculative')} [{res.get('trust_score', 0.5)}])"
    except Exception as e:
        kg_status = f"⚠️ FalkorDB KG skipped ({type(e).__name__}: {e})"

    return (
        f"✅ Recorded: '{episode_name}'\n"
        f"   → Journal: {journal_file}\n"
        f"   → {kg_status}"
    )


# ── Tool 3: Dream Mode ─────────────────────────────────────────────────────

@mcp.tool(
    description=(
        "Trigger an on-demand Cerebrum Dream Mode consolidation cycle. Executes: "
        "(1) Synaptic pruning & stale fact contradiction resolution, archiving invalid facts to disk, "
        "(2) Graph community detection (Louvain algorithm) clustering code symbols into subsystems, "
        "(3) Abstract invariant induction across codebase decisions, and "
        "(4) Generates a dated dream report in cerebrum/journal/dreams/."
    )
)
async def trigger_dream_mode(
    project: str = "cerebrum",
    purge_stale: bool = False,
    invariants: Optional[list[dict[str, str]]] = None,
    stale_fact_names: Optional[list[str]] = None,
) -> str:
    """
    Args:
        project:          Target project label (default: 'cerebrum').
        purge_stale:      If True, physically removes superseded facts after archiving. Default False (soft-prune).
        invariants:       Optional list of newly induced architectural invariants: [{'domain': '...', 'rule': '...', 'rationale': '...'}].
        stale_fact_names: Optional list of older fact names to supersede during pruning.
    Returns:
        Structured summary of the dream consolidation report.
    """
    from cerebrum.dream import CerebrumDreamEngine
    engine = CerebrumDreamEngine()
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
) -> str:
    """
    Args:
        path:             Absolute path to the directory to index.
        collection:       Optional Qdrant collection name (defaults to 'cerebrum_codebase').
        symbols_graph:    Optional FalkorDB symbol graph name (defaults to '<collection>_symbols').
        exclude_patterns: Additional glob patterns to exclude (e.g. ['tests/', '*.spec.ts']).
    Returns:
        Confirmation with document count.
    """
    if not Path(path).exists():
        return f"❌ Path does not exist: {path}"
    target_col = collection or os.getenv("QDRANT_COLLECTION", "cerebrum_codebase")
    target_sym = symbols_graph or (f"{target_col}_symbols" if target_col != "cerebrum_codebase" else "cerebrum_symbols")
    asyncio.create_task(_ingest(path, extra_excludes=exclude_patterns or [], collection=target_col, symbols_graph=target_sym))
    return f"🚀 Indexing started in background for '{path}' into Qdrant collection '{target_col}' and FalkorDB graph '{target_sym}'."


# ── Tool 5: Health ─────────────────────────────────────────────────────────

@mcp.tool(
    description=(
        "Check the health of all Cerebrum backend services. Returns a JSON status "
        "report for Qdrant, FalkorDB, the inference server (embeddings/reranker), and the dashboard. "
        "Call this if other Cerebrum tools return errors or time out."
    )
)
async def check_cerebrum_health() -> str:
    """Returns JSON with status of each service."""
    import httpx
    import socket

    status = {}

    # Dynamic service URLs
    qdrant_url = os.getenv("QDRANT_URL", "http://localhost:6333").rstrip("/")
    embed_url = os.getenv("EMBED_BASE_URL", "http://127.0.0.1:8000/v1")
    base_host = embed_url.replace("/v1", "").rstrip("/")
    inference_health = os.getenv(
        "INFERENCE_HEALTH_URL",
        f"{base_host}/health" if ("localhost" in base_host or "127.0.0.1" in base_host) else embed_url
    )
    inference_health = inference_health.replace("://localhost", "://127.0.0.1")

    # Check inference server & dashboard HTTP
    dash_host = os.getenv("DASHBOARD_HOST", "127.0.0.1")
    dash_port = os.getenv("DASHBOARD_PORT", "8004")

    async with httpx.AsyncClient(timeout=5.0) as client:
        # 1. Qdrant check (Embedded vs Remote)
        qdrant_url = os.getenv("QDRANT_URL")
        if not qdrant_url:
            from pathlib import Path
            qpath = Path.home() / ".cerebrum" / "qdrant"
            meta_file = qpath / "meta.json"
            if meta_file.is_file():
                try:
                    import json
                    meta_data = json.loads(meta_file.read_text(encoding="utf-8"))
                    col_names = list(meta_data.get("collections", {}).keys())
                    status["qdrant"] = f"✅ EMBEDDED ({len(col_names)} collections: {', '.join(col_names)})"
                except Exception as e:
                    status["qdrant"] = f"⚠️ EMBEDDED (meta read error: {e})"
            elif qpath.is_dir():
                status["qdrant"] = "✅ EMBEDDED (directory active)"
            else:
                status["qdrant"] = "❌ DOWN (Storage path missing)"
        else:
            try:
                resp = await client.get(f"{qdrant_url.rstrip('/')}/healthz")
                status["qdrant"] = "✅ RUNNING" if resp.status_code < 500 else f"⚠️  HTTP {resp.status_code}"
            except Exception as e:
                status["qdrant"] = f"❌ DOWN ({type(e).__name__})"

        # 2. Inference server check
        try:
            resp = await client.get(inference_health)
            status["inference_server"] = "✅ RUNNING" if resp.status_code < 500 else f"⚠️  HTTP {resp.status_code}"
        except Exception as e:
            status["inference_server"] = f"❌ DOWN ({type(e).__name__})"

        # 3. Dashboard check
        try:
            resp = await client.get(f"http://{dash_host}:{dash_port}/api/cache/stats")
            status["cerebrum_dashboard"] = "✅ RUNNING" if resp.status_code < 500 else f"⚠️  HTTP {resp.status_code}"
        except Exception as e:
            status["cerebrum_dashboard"] = f"❌ DOWN ({type(e).__name__})"

    # FalkorDB check (Unix Domain Socket first, then TCP)
    from pathlib import Path
    falkor_sock = Path.home() / ".cerebrum" / "run" / "falkordb.sock"
    if falkor_sock.is_socket():
        try:
            import redis
            r = redis.Redis(unix_socket_path=str(falkor_sock), socket_timeout=2.0)
            if r.ping():
                status["falkordb"] = "✅ RUNNING (Unix Socket)"
            else:
                status["falkordb"] = "⚠️ Socket Ping Failed"
        except Exception as e:
            status["falkordb"] = f"❌ DOWN ({e})"
    else:
        falkor_host = os.getenv("FALKORDB_HOST", "127.0.0.1")
        falkor_port = int(os.getenv("FALKORDB_PORT", "6379"))
        try:
            sock = socket.create_connection((falkor_host, falkor_port), timeout=2)
            sock.close()
            status["falkordb"] = "✅ RUNNING (TCP :6379)"
        except Exception as e:
            status["falkordb"] = f"❌ DOWN ({e})"

    # Grounded invariant drift check
    try:
        from cerebrum.invariants import InvariantGroundingEngine
        inv_eng = InvariantGroundingEngine()
        drift_res = inv_eng.audit_invariant_drift()
        status["invariants"] = (
            f"✅ {drift_res['verified_count']} verified, {drift_res['drifted_count']} drifted, "
            f"{drift_res['orphaned_count']} orphaned (total: {drift_res['total_grounded']})"
        )
        if drift_res["drifted_count"] > 0:
            status["recommendation"] = (
                f"⚠️ {drift_res['drifted_count']} architectural invariant(s) drifted from live AST bodies. "
                f"Run trigger_dream_mode() to review and consolidate."
            )
    except Exception as e:
        status["invariants"] = f"⚠️ Check skipped ({type(e).__name__}: {e})"

    # Overall recommendation
    if any("❌ DOWN" in str(v) for v in status.values()):
        status["recommendation"] = f"⚠️  One or more Cerebrum services are down. Run 'cerebrum start' to bring them online."
    elif "recommendation" not in status:
        status["recommendation"] = "✅ All core Cerebrum services are operational."

    return json.dumps(status, indent=2)


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
        symbols_graph: Optional FalkorDB graph name (defaults to 'cerebrum_symbols').
        token_budget:  Optional max tokens for the response (default: 1500).
    Returns:
        Structured JSON report showing all impacted files, lines, relationships, and progressive summary.
    """
    target_graph = symbols_graph or os.getenv("FALKORDB_SYMBOLS_GRAPH", "cerebrum_symbols")
    mgr = symbol_graph if target_graph == symbol_graph.graph_name else SymbolGraphManager(graph_name=target_graph)
    impact = mgr.trace_symbol_impact(symbol, direction=direction, max_depth=max_depth, token_budget=token_budget)
    return json.dumps(impact, indent=2)


# ── Tool 8: Anti-Ripgrep Deterministic Symbol Seek ───────────────────────

@mcp.tool(
    description=(
        "Deterministic symbol locator replacing brute-force ripgrep loops. "
        "Looks up exact symbol declaration, signature, docstring, callers, and callees "
        "directly from the compiler AST knowledge graph in FalkorDB in <2ms, consuming <150 tokens."
    )
)
async def seek_symbol(symbol_name: str, file_hint: Optional[str] = None) -> str:
    """
    Args:
        symbol_name: Name or qualified name of the symbol (function, class, struct, method).
        file_hint: Optional filename or path substring to disambiguate identical symbols.
    Returns:
        Structured JSON declaration and immediate call graph.
    """
    from cerebrum.symbols.seek import SymbolSeekEngine
    seeker = SymbolSeekEngine()
    return seeker.seek_symbol(symbol_name, file_hint=file_hint)


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
) -> str:
    """
    Args:
        action: 'create', 'get_ready', 'update_status', or 'list_all'.
        title: Task title for 'create'.
        description: Task requirements and verification criteria for 'create'.
        complexity: Estimated complexity score 1-10.
        assigned_to: Target subagent persona (e.g. 'cerebrum-task-runner').
        depends_on: List of upstream prerequisite task IDs.
        task_id: Target task ID for 'update_status'.
        status: New state ('pending', 'ready', 'in_progress', 'completed', 'failed').
        error: Failure explanation if status is 'failed'.
    Returns:
        JSON response with task details, ready tasks, or operation confirmation.
    """
    from cerebrum.tasks.tracker import TaskDAGTracker
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
        )
        return json.dumps({"status": "created", "task_id": tid})

    elif act in ("get_ready", "ready"):
        ready = tracker.get_ready_tasks()
        return json.dumps({"ready_tasks": ready}, indent=2)

    elif act == "update_status":
        if not task_id or not status:
            return json.dumps({"error": "Missing 'task_id' or 'status'"})
        ok = tracker.update_task_status(task_id, status=status, error=error)
        return json.dumps({"task_id": task_id, "updated": ok, "status": status})

    return json.dumps({"error": f"Unknown action: {action}"})


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
    import uuid
    now = datetime.now(timezone.utc).isoformat()
    action_norm = action.lower().strip()

    if action_norm == "create":
        bid = f"baton_{datetime.now().strftime('%Y%m%d_%H%M%S')}_{uuid.uuid4().hex[:6]}"
        data = {
            "baton_id": bid,
            "created_at": now,
            "source_agent": "antigravity",
            "target_agent": target_agent or "any",
            "current_scope": current_scope or "",
            "open_hypotheses": open_hypotheses or [],
            "unresolved_questions": unresolved_questions or [],
            "active_blast_radius": active_blast_radius or [],
            "status": "pending",
        }
        baton_path = HANDOFFS_DIR / f"{bid}.json"
        with open(baton_path, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2)

        return (
            f"✅ Created cross-agent handoff baton: {bid}\n"
            f"   → Target: {data['target_agent']}\n"
            f"   → Scope: {data['current_scope']}\n"
            f"   → Open hypotheses: {len(data['open_hypotheses'])}\n"
            f"   → Unresolved questions: {len(data['unresolved_questions'])}\n"
            f"   → Active blast radius: {len(data['active_blast_radius'])}\n"
            f"   → Path: {baton_path}"
        )

    elif action_norm == "read":
        files = sorted(HANDOFFS_DIR.glob("baton_*.json"), reverse=True)
        if not files:
            return "⚠️ No cross-agent handoff batons found in journal/handoffs/."

        target_file = None
        if baton_id:
            for f in files:
                if baton_id in f.name:
                    target_file = f
                    break
        else:
            for f in files:
                try:
                    with open(f, "r", encoding="utf-8") as jf:
                        d = json.load(jf)
                    if d.get("status") == "pending":
                        if not target_agent or d.get("target_agent") in (target_agent, "any"):
                            target_file = f
                            break
                except Exception:
                    continue

        if not target_file:
            return f"⚠️ No matching handoff baton found (baton_id={baton_id}, target_agent={target_agent})."

        with open(target_file, "r", encoding="utf-8") as jf:
            data = json.load(jf)
        return json.dumps(data, indent=2)

    elif action_norm == "list":
        files = sorted(HANDOFFS_DIR.glob("baton_*.json"), reverse=True)
        summaries = []
        for f in files[:10]:
            try:
                with open(f, "r", encoding="utf-8") as jf:
                    d = json.load(jf)
                summaries.append({
                    "baton_id": d.get("baton_id"),
                    "created_at": d.get("created_at"),
                    "target_agent": d.get("target_agent"),
                    "current_scope": d.get("current_scope"),
                    "status": d.get("status"),
                })
            except Exception:
                pass
        return json.dumps({"pending_batons": summaries}, indent=2)

    elif action_norm == "complete":
        if not baton_id:
            return "⚠️ Please provide baton_id to mark complete."
        matched = list(HANDOFFS_DIR.glob(f"*{baton_id}*.json"))
        if not matched:
            return f"⚠️ Baton '{baton_id}' not found."
        with open(matched[0], "r", encoding="utf-8") as jf:
            data = json.load(jf)
        data["status"] = "completed"
        data["completed_at"] = now
        with open(matched[0], "w", encoding="utf-8") as jf:
            json.dump(data, jf, indent=2)
        return f"✅ Handoff baton '{data['baton_id']}' marked as completed."

    return f"⚠️ Unknown action '{action}'. Use create, read, list, or complete."


# ── Entry point ────────────────────────────────────────────────────────────

def main():
    import argparse
    parser = argparse.ArgumentParser(description="Cerebrum FastMCP Server")
    parser.add_argument("--transport", default=os.getenv("MCP_TRANSPORT", "stdio"), choices=["stdio", "sse"], help="MCP transport protocol (stdio or sse)")
    parser.add_argument("--port", type=int, default=int(os.getenv("MCP_PORT", os.getenv("CEREBRUM_MCP_PORT", "8005"))), help="Port for SSE transport")
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
            print(f"[Cerebrum Server] Starting FastMCP on SSE transport at http://{args.host}:{args.port}")
            mcp.run(transport="sse", host=args.host, port=args.port)
        else:
            mcp.run(transport="stdio")
    except (KeyboardInterrupt, SystemExit):
        os._exit(0)


if __name__ == "__main__":
    main()
