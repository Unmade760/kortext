"""
Cerebrum HippoRAG Engine: Personalized PageRank over Entity & Symbol Knowledge Graphs.
Executes single-pass multi-hop associative retrieval in <30ms without iterative LLM calls.
"""

from __future__ import annotations

import logging
import time
from typing import Dict, List, Optional, Set, Tuple

import numpy as np

from cerebrum.falkordb_client import get_shared_falkordb_client

logger = logging.getLogger("cerebrum.hipporag")


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
        graph_name: str = "cerebrum",
    ) -> List[Tuple[str, float]]:
        """
        Runs single-pass Personalized PageRank starting from seed entities.
        Applies Inverse Degree Specificity (IDS) so that high-degree generic hubs are prevented
        from drowning out domain-specific needles.
        """
        if not seed_entities:
            return []

        t0 = time.perf_counter()
        clean_seeds = [s.replace("'", "\\'") for s in seed_entities]
        seed_clause = ", ".join([f"'{s}'" for s in clean_seeds])

        # Multi-Hop Association Cypher Query: Traverses entities and linked code symbols
        cypher = f"""
        MATCH (seed)
        WHERE (seed:Entity OR seed:Symbol) AND seed.name IN [{seed_clause}]
        OPTIONAL MATCH (seed)-[r:RELATES_TO|CALLS|IMPORTS|DEFINED_IN|AFFECTS_SYMBOL]-(neighbor)
        OPTIONAL MATCH (neighbor)-[r2:RELATES_TO|CALLS|IMPORTS]-(second)
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
        WHERE (seed:Entity OR seed:Symbol) AND seed.name IN [{seed_clause}]
        MATCH (seed)-[:RELATES_TO|CALLS|AFFECTS_SYMBOL]-(neighbor)
        MATCH (neighbor)-[r2:RELATES_TO|CALLS]-(second)
        RETURN 
            neighbor.name AS source, 
            second.name AS target, 
            0.6 AS weight
        """

        raw_graph = self.client.query(graph_name, cypher)
        if not raw_graph or len(raw_graph) < 2 or not raw_graph[1]:
            # Fallback: return uniform distribution over seeds
            return [(s, 1.0 / len(seed_entities)) for s in seed_entities]

        # 1. Build Adjacency Matrix & Disambiguated Node Index
        nodes: Set[str] = set()
        edges: List[Tuple[str, str, float]] = []

        for row in raw_graph[1]:
            if not row or len(row) < 3 or row[0] is None or row[1] is None:
                continue
            src, tgt = str(row[0]), str(row[1])
            wt = float(row[2]) if row[2] is not None else 1.0
            nodes.add(src)
            nodes.add(tgt)
            edges.append((src, tgt, wt))

        node_list = sorted(list(nodes))
        node_idx = {name: i for i, name in enumerate(node_list)}
        n = len(node_list)

        if n == 0:
            return []

        # 2. Build Column-Normalized Transition Matrix M
        out_degree = np.zeros(n, dtype=np.float32)
        for src, tgt, wt in edges:
            out_degree[node_idx[src]] += wt

        M = np.zeros((n, n), dtype=np.float32)
        for src, tgt, wt in edges:
            u, v = node_idx[src], node_idx[tgt]
            if out_degree[u] > 0:
                M[v, u] = wt / out_degree[u]

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
            p_next = (1.0 - self.alpha) * (M @ p) + self.alpha * p0
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
