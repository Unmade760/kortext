"""
Native async state pipeline orchestrator.

.. deprecated:: 2.0.0
    `KortextPipeline` (and legacy `CerebrumPipeline`) and `make_graph` are deprecated and superseded by
    `RetrievalEngine.federated_query` (see `kortext.retrieval.engine`).
    This module is preserved for backward compatibility with existing scripts.

Flow: parallel_fetch → synthesize

parallel_fetch runs four retrieval nodes concurrently:
  - Node A (Episodic)  : Agent-native episodic temporal facts
  - Node B (Viking)    : tree-sitter structural context
  - Node C (Factual)   : Qdrant + reranker code snippets
  - Node D (Symbols)   : FalkorDB AST symbol graph lookup

synthesize merges all results into a structured Markdown block.
"""
from __future__ import annotations

import asyncio
import logging
import re
import warnings
from pathlib import Path
from typing import Any, Dict, List, Optional, TypedDict

from typing_extensions import deprecated

from kortext.retrieval import RetrievalEngine
from kortext.episodic import AgentNativeEpisodicDriver
from kortext.symbols.graph import SymbolGraphManager
from kortext.symbols.seek import extract_symbol_candidates, _extract_symbol_candidates

logger = logging.getLogger(__name__)


# ── Typed state ────────────────────────────────────────────────────────────

@deprecated("KortextState is deprecated; superseded by RetrievalEngine.federated_query structures.")
class KortextState(TypedDict, total=False):
    """Execution state dictionary for Kortext pipeline.

    .. deprecated:: 2.0.0
        Superseded by `RetrievalEngine.federated_query` result envelopes.
    """
    query: str
    collection: Optional[str]
    workspace_root: Optional[str]
    kg_facts: List[str]
    viking_summaries: str
    doc_snippets: List[str]
    symbol_results: List[Dict[str, Any]]
    final_context: str


CerebrumState = KortextState  # Backwards compatibility alias
CortexState = KortextState  # Backwards compatibility alias


# ── Native Async Pipeline ──────────────────────────────────────────────────

@deprecated("KortextPipeline is deprecated and superseded by RetrievalEngine.federated_query.")
class KortextPipeline:
    """Native async pipeline for unified 4-tier memory retrieval and synthesis.

    .. deprecated:: 2.0.0
        `KortextPipeline` is superseded by `RetrievalEngine.federated_query`.
        Use `RetrievalEngine().federated_query(...)` directly for unified memory retrieval.
    """

    def __init__(
        self,
        retrieval: RetrievalEngine,
        viking: Optional[Any] = None,
        episodic: Optional[AgentNativeEpisodicDriver] = None,
        symbol_graph: Optional[SymbolGraphManager] = None,
    ):
        self.retrieval = retrieval
        self.viking = viking
        self.episodic = episodic
        self.symbol_graph = symbol_graph if symbol_graph is not None else SymbolGraphManager()

    async def parallel_fetch(self, state: KortextState) -> dict:
        """Run all four fetch operations concurrently."""

        query = state.get("query", "")

        async def fetch_episodic():
            try:
                return await self.episodic.search(query)
            except Exception as e:
                logger.error(f"[Kortext/Episodic] Error: {e}")
                return []

        async def fetch_viking():
            return ""

        async def fetch_retrieval():
            try:
                target_col = state.get("collection")
                return await self.retrieval.query(query, collection=target_col)
            except Exception as e:
                logger.error(f"[Kortext/Retrieval] Error: {e}")
                return []

        async def fetch_symbols():
            if not self.symbol_graph:
                return []
            target_col = state.get("collection")
            from kortext.retrieval.engine import resolve_symbol_graph_for_collection
            target_sym_db = resolve_symbol_graph_for_collection(target_col)

            active_sym_graph = self.symbol_graph
            current_sym_db = getattr(self.symbol_graph, "graph_name", "")
            if (
                target_sym_db
                and target_sym_db != current_sym_db
                and not (target_sym_db in ("kortext_symbols", "cerebrum_symbols") and current_sym_db in ("kortext_symbols", "cerebrum_symbols"))
            ):
                from kortext.symbols.graph import SymbolGraphManager
                active_sym_graph = SymbolGraphManager(graph_name=target_sym_db)

            candidates = extract_symbol_candidates(query)
            if not candidates:
                return []
            loop = asyncio.get_running_loop()

            async def _lookup(cand: str):
                try:
                    return await loop.run_in_executor(None, active_sym_graph.find_references, cand)
                except Exception as e:
                    logger.error(f"[Kortext/Symbols] Error resolving '{cand}': {e}")
                    return None

            results = await asyncio.gather(*[_lookup(c) for c in candidates])
            return [
                r for r in results
                if r and isinstance(r, dict) and (r.get("definitions") or r.get("references") or r.get("imports"))
            ]

        kg_facts, viking_summaries, doc_snippets, symbol_results = await asyncio.gather(
            fetch_episodic(),
            fetch_viking(),
            fetch_retrieval(),
            fetch_symbols(),
        )
        return {
            "kg_facts": kg_facts,
            "viking_summaries": viking_summaries,
            "doc_snippets": doc_snippets,
            "symbol_results": symbol_results,
        }

    def synthesize(self, state: KortextState) -> dict:
        """Merge all sources into structured Markdown blocks."""
        kg_facts = state.get("kg_facts") or []
        facts_md = (
            "\n".join(f"- {f}" for f in kg_facts)
            if kg_facts
            else "_No relevant operational facts found._"
        )
        doc_snippets = state.get("doc_snippets") or []
        snippets_md = (
            "\n\n".join(f"```\n{s}\n```" for s in doc_snippets)
            if doc_snippets
            else "_No code references found._"
        )
        viking_md = state.get("viking_summaries") or "_No structural context available._"

        # Format deterministic code symbols
        symbol_results = state.get("symbol_results") or []
        symbol_section = ""
        if symbol_results:
            blocks = []
            for item in symbol_results:
                sym = item.get("symbol", "")
                defs = item.get("definitions", [])
                imports = item.get("imports", [])
                refs = item.get("references", [])

                lines = [f"- **`{sym}`**"]
                if defs:
                    for d in defs:
                        fp = d.get("file_path", "")
                        ln = d.get("line", 1)
                        kind = d.get("kind", "symbol")
                        sig = d.get("signature", "")
                        doc = d.get("docstring", "")
                        parent = d.get("parent")
                        parent_info = f" in `{parent}`" if parent else ""
                        lines.append(f"  - **Definition ({kind}{parent_info})**: [{fp}:{ln}](file://{fp}#L{ln})")
                        if sig:
                            lines.append(f"    - Signature: `{sig}`")
                        if doc:
                            lines.append(f"    - Docstring: {doc}")
                else:
                    lines.append("  - **Definition**: _External or unindexed declaration_")

                if imports:
                    lines.append(f"  - **Imported by ({len(imports)} file(s))**:")
                    for imp in imports[:8]:
                        fp = imp.get("file_path", "")
                        ln = imp.get("line", 1)
                        mod = imp.get("module") or ""
                        mod_info = f" (from `{mod}`)" if mod else ""
                        lines.append(f"    - [{fp}:{ln}](file://{fp}#L{ln}){mod_info}")
                    if len(imports) > 8:
                        lines.append(f"    - _... and {len(imports) - 8} more files_")

                if refs:
                    lines.append(f"  - **Cross-File References & Calls ({len(refs)} site(s))**:")
                    for r in refs[:10]:
                        fp = r.get("file_path", "")
                        ln = r.get("line", 1)
                        kind = r.get("kind", "call")
                        lines.append(f"    - [{fp}:{ln}](file://{fp}#L{ln}) ({kind})")
                    if len(refs) > 10:
                        lines.append(f"    - _... and {len(refs) - 10} more call sites_")

                backlinks = item.get("backlinks", [])
                if backlinks:
                    lines.append(f"  - **Referenced in Documentation Notes ({len(backlinks)} note(s))**:")
                    for bl in backlinks[:8]:
                        fp = bl.get("file_path", "")
                        ln = bl.get("line", 1)
                        doc_t = bl.get("doc_title") or Path(fp).name
                        lbl = bl.get("label", "")
                        ltype = bl.get("link_type", "wiki_link")
                        lbl_info = f" (via `{ltype}`: \"{lbl}\")" if lbl else ""
                        lines.append(f"    - [{doc_t} ({fp}:{ln})](file://{fp}#L{ln}){lbl_info}")
                    if len(backlinks) > 8:
                        lines.append(f"    - _... and {len(backlinks) - 8} more note links_")

                blocks.append("\n".join(lines))

            symbol_section = f"""### Deterministic Code Symbols & Cross-File References (FalkorDB)
{chr(10).join(blocks)}

"""

        final_context = f"""{symbol_section}### Operational Facts & Decisions (Graphiti)
{facts_md}

### System Architecture Overview (OpenViking)
{viking_md}

### Ground-Truth Code References (Qdrant Reranked)
{snippets_md}"""

        return {"final_context": final_context}

    async def ainvoke(self, state: KortextState) -> dict:
        """Execute parallel_fetch followed by synthesize using native asyncio."""
        fetch_results = await self.parallel_fetch(state)
        merged_state: KortextState = {**state, **fetch_results}
        syn_result = self.synthesize(merged_state)
        return {"final_context": syn_result["final_context"]}


CerebrumPipeline = KortextPipeline  # Backwards compatibility alias


# ── Pipeline factory ───────────────────────────────────────────────────────

@deprecated("make_graph is deprecated and superseded by RetrievalEngine.federated_query.")
def make_graph(
    retrieval: RetrievalEngine,
    viking: Optional[Any] = None,
    episodic: Optional[AgentNativeEpisodicDriver] = None,
    symbol_graph: Optional[SymbolGraphManager] = None,
) -> KortextPipeline:
    """Build and return the Kortext native async pipeline.

    .. deprecated:: 2.0.0
        `make_graph` is deprecated and superseded by `RetrievalEngine.federated_query`.
        Call `retrieval.federated_query(...)` directly.
    """
    return KortextPipeline(
        retrieval=retrieval,
        viking=viking,
        episodic=episodic,
        symbol_graph=symbol_graph,
    )


__all__ = [
    "KortextState",
    "CerebrumState",
    "CortexState",
    "KortextPipeline",
    "CerebrumPipeline",
    "make_graph",
    "extract_symbol_candidates",
    "_extract_symbol_candidates",
]
