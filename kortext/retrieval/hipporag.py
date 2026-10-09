"""
Kortext HippoRAG Engine: Personalized PageRank over Entity & Symbol Knowledge Graphs.
Executes single-pass multi-hop associative retrieval in <30ms without iterative LLM calls.
"""

from __future__ import annotations

import logging
import os
import time
from typing import Any, Dict, List, Optional, Set, Tuple

import numpy as np
import scipy.sparse as sp

from kortext.falkordb_client import get_shared_falkordb_client

logger = logging.getLogger("kortext.hipporag")


_DEFAULT_SYMBOLS = object()


class HippoRAGPPR:
    """
    Executes Personalized PageRank (PPR) with Inverse Degree Specificity (IDS)
    over unified symbol and episodic entity knowledge graphs.
    """

    def __init__(
        self,
        damping: float = 0.5,
        max_iterations: int = 15,
        tolerance: float = 1e-6,
    ):
        self.alpha = damping
        self.max_iter = max_iterations
        self.tol = tolerance
        self.client = get_shared_falkordb_client()

    def retrieve_associative_subgraph(
        self,
        seed_entities: List[str],
        top_k: int = 15,
        graph_name: str = os.getenv("KORTEXT_DATABASE", os.getenv("FALKORDB_DATABASE", "kortext")),
        symbols_graph: Any = _DEFAULT_SYMBOLS,
        edge_types: Optional[List[str]] = None,
    ) -> List[Tuple[str, float]]:
        """
        Runs single-pass Personalized PageRank starting from seed entities.
        Applies Inverse Degree Specificity (IDS) so that high-degree generic hubs are prevented
        from drowning out domain-specific needles.

        When graph_name is 'kortext' (or legacy 'cerebrum') and AST relations/code symbols are queried,
        traverses kortext_symbols (or legacy cerebrum_symbols) as well and merges associative edges into the PPR adjacency matrix.
        Degrades gracefully if one of the graphs is empty or unavailable.
        """
        if not seed_entities:
            return []

        if symbols_graph is _DEFAULT_SYMBOLS:
            if graph_name in ("cerebrum", "cerebrum_codebase"):
                symbols_graph = os.getenv("FALKORDB_SYMBOLS_GRAPH", "cerebrum_symbols")
            else:
                symbols_graph = os.getenv("KORTEXT_SYMBOLS_GRAPH", os.getenv("FALKORDB_SYMBOLS_GRAPH", "kortext_symbols"))

        t0 = time.perf_counter()

        # Multi-Hop Association Cypher Query: Traverses entities and linked code symbols
        cypher = """
        MATCH (seed)
        WHERE (seed:Entity OR seed:Symbol) AND seed.name IN $seeds
        OPTIONAL MATCH (seed)-[r:RELATES_TO|CALLS|IMPORTS|DEFINED_IN|AFFECTS_SYMBOL]-(neighbor)
        RETURN 
            seed.name AS source, 
            neighbor.name AS target, 
            CASE 
                WHEN type(r) = 'CALLS' THEN 1.0
                WHEN type(r) = 'DEFINED_IN' THEN 1.0
                WHEN type(r) = 'AFFECTS_SYMBOL' THEN 0.9
                ELSE 0.8 
            END AS weight
        UNION
        MATCH (seed)
        WHERE (seed:Entity OR seed:Symbol) AND seed.name IN $seeds
        MATCH (seed)-[:RELATES_TO|CALLS|AFFECTS_SYMBOL]-(neighbor)
        MATCH (neighbor)-[r2:RELATES_TO|CALLS]-(second)
        RETURN 
            neighbor.name AS source, 
            second.name AS target, 
            0.6 AS weight
        """

        ast_edge_types = {"CALLS", "IMPORTS", "DEFINED_IN", "REFERENCES"}
        should_traverse_symbols = (
            symbols_graph is not None
            and symbols_graph != graph_name
            and graph_name in ("kortext", "cerebrum")
            and (
                edge_types is None
                or any(e.upper() in ast_edge_types for e in edge_types)
                or any(s.isidentifier() for s in seed_entities)
            )
        )

        raw_graphs = []

        # 1. Query primary graph (e.g. "kortext")
        try:
            raw_primary = self.client.query(graph_name, cypher, {"seeds": seed_entities})
            if raw_primary and len(raw_primary) > 1 and raw_primary[1]:
                raw_graphs.append(raw_primary)
        except Exception as e:
            logger.debug(f"HippoRAG primary graph query failed on '{graph_name}': {e}")

        # 2. Query code symbols graph (e.g. "kortext_symbols") if enabled
        if should_traverse_symbols and symbols_graph:
            try:
                raw_symbols = self.client.query(symbols_graph, cypher, {"seeds": seed_entities})
                if raw_symbols and len(raw_symbols) > 1 and raw_symbols[1]:
                    raw_graphs.append(raw_symbols)
            except Exception as e:
                logger.debug(f"HippoRAG symbols graph query failed on '{symbols_graph}': {e}")

        if not raw_graphs:
            # Fallback: return uniform distribution over seeds
            return [(s, 1.0 / len(seed_entities)) for s in seed_entities]

        # 1. Build Adjacency Matrix & Disambiguated Node Index
        nodes: Set[str] = set()
        edge_dict: Dict[Tuple[str, str], float] = {}

        for raw_graph in raw_graphs:
            for row in raw_graph[1]:
                if not row or len(row) < 3 or row[0] is None or row[1] is None:
                    continue
                src, tgt = str(row[0]), str(row[1])
                wt = float(row[2]) if row[2] is not None else 1.0
                nodes.add(src)
                nodes.add(tgt)
                edge_dict[(src, tgt)] = max(edge_dict.get((src, tgt), 0.0), wt)

        edges: List[Tuple[str, str, float]] = [
            (src, tgt, wt) for (src, tgt), wt in edge_dict.items()
        ]

        node_list = sorted(list(nodes))
        node_idx = {name: i for i, name in enumerate(node_list)}
        n = len(node_list)

        if n == 0 or not edges:
            return [(s, 1.0 / len(seed_entities)) for s in seed_entities]

        # 2. Build Column-Normalized Transition Matrix M (Sparse CSR)
        out_degree = np.zeros(n, dtype=np.float32)
        for src, tgt, wt in edges:
            out_degree[node_idx[src]] += wt

        rows = []
        cols = []
        data = []
        for src, tgt, wt in edges:
            u, v = node_idx[src], node_idx[tgt]
            if out_degree[u] > 0:
                rows.append(v)
                cols.append(u)
                data.append(wt / out_degree[u])

        M = sp.csr_matrix((data, (rows, cols)), shape=(n, n), dtype=np.float32)

        # 3. Construct Inverse Degree Specificity (IDS) Seed Vector p0
        p0 = np.zeros(n, dtype=np.float32)
        for s in seed_entities:
            if s in node_idx:
                idx = node_idx[s]
                # Inverse Degree Specificity: rare nodes get higher initial probability mass
                p0[idx] = 1.0 / max(out_degree[idx], 1.0)

        p0_sum = np.sum(p0)
        if p0_sum > 0:
            p0 = p0 / p0_sum
        else:
            p0 = np.ones(n, dtype=np.float32) / n

        # 4. High-Performance Power Iteration Loop
        p = np.copy(p0)
        for iteration in range(self.max_iter):
            p_next = (1.0 - self.alpha) * (M.dot(p)) + self.alpha * p0
            diff = np.linalg.norm(p_next - p, ord=1)
            p = p_next
            if diff < self.tol:
                break

        # 5. Extract and Rank Top-K Associative Nodes
        ranked_indices = np.argsort(-p)[:top_k]
        results = [(node_list[i], float(p[i])) for i in ranked_indices if p[i] > 1e-5]

        elapsed_ms = (time.perf_counter() - t0) * 1000
        logger.debug(f"HippoRAG PPR completed in {elapsed_ms:.2f}ms across {n} nodes.")
        return results
