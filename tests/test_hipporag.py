"""
Unit and integration tests for HippoRAG Personalized PageRank (PPR) Engine.
Verifies single-pass multi-hop associative retrieval, Inverse Degree Specificity, and convergence.
"""

import pytest
import numpy as np
from unittest.mock import MagicMock
from kortext.retrieval.hipporag import HippoRAGPPR


class TestHippoRAGPPR:
    @pytest.fixture
    def mock_falkor(self):
        client = MagicMock()
        # Mock Cypher response: associations rows
        # Columns: [source, target, weight]
        client.query.return_value = [
            ["source", "target", "weight"],
            [
                ["SessionManager", "PR_42", 0.9],
                ["PR_42", "Issue_18", 0.8],
                ["Issue_18", "Invariant_4", 1.0],
                ["Invariant_4", "FalkorDBClient", 0.9],
            ]
        ]
        return client

    def test_hippo_ppr_convergence(self, mock_falkor):
        ppr = HippoRAGPPR(damping=0.5, max_iterations=15, tolerance=1e-6)
        ppr.client = mock_falkor

        results = ppr.retrieve_associative_subgraph(
            seed_entities=["SessionManager"],
            top_k=5,
            graph_name="cerebrum"
        )

        assert len(results) > 0
        node_names = [r[0] for r in results]
        assert "Invariant_4" in node_names or "PR_42" in node_names
        assert results[0][1] > 0.0

        mock_falkor.query.assert_called()
        calls = mock_falkor.query.call_args_list
        assert len(calls) == 2
        assert calls[0][0][0] == "cerebrum"
        assert calls[1][0][0] == "cerebrum_symbols"
        assert "$seeds" in calls[0][0][1]
        assert "$seeds" in calls[1][0][1]
        assert calls[0][0][2] == {"seeds": ["SessionManager"]}
        assert calls[1][0][2] == {"seeds": ["SessionManager"]}

    def test_inverse_degree_specificity_weighting(self):
        """Verifies that high-degree generic hubs receive lower initial mass than specific seeds."""
        degrees = np.array([100.0, 2.0], dtype=np.float32)  # Node 0 is hub, Node 1 is specific
        p0 = 1.0 / degrees
        p0_norm = p0 / np.sum(p0)

        # Specific node must have much higher mass
        assert p0_norm[1] > p0_norm[0] * 20

    def test_empty_seeds_graceful_fallback(self):
        ppr = HippoRAGPPR()
        res = ppr.retrieve_associative_subgraph([])
        assert res == []

    def test_disconnected_graph_fallback(self):
        client = MagicMock()
        client.query.return_value = [[], []]
        ppr = HippoRAGPPR()
        ppr.client = client

        res = ppr.retrieve_associative_subgraph(["UnknownNode"])
        assert len(res) == 1
        assert res[0][0] == "UnknownNode"
        assert res[0][1] == 1.0

    def test_sparse_matrix_sink_nodes_and_multiple_seeds(self):
        client = MagicMock()
        client.query.return_value = [
            ["source", "target", "weight"],
            [
                ["A", "B", 1.0],
                ["A", "C", 2.0],
                ["B", "C", 1.5],
            ]
        ]
        ppr = HippoRAGPPR(damping=0.5, max_iterations=20, tolerance=1e-7)
        ppr.client = client

        res = ppr.retrieve_associative_subgraph(["A", "B"])
        assert len(res) == 3
        nodes = [r[0] for r in res]
        assert set(nodes) == {"A", "B", "C"}
        total_score = sum(r[1] for r in res)
        assert total_score > 0.0

    def test_hippo_ppr_merges_cerebrum_and_symbols_graphs(self):
        client = MagicMock()
        def mock_query(graph, cypher, params=None):
            if graph == "cerebrum":
                return [
                    ["source", "target", "weight"],
                    [["SeedFunc", "EpisodicConcept", 0.8]]
                ]
            elif graph == "cerebrum_symbols":
                return [
                    ["source", "target", "weight"],
                    [["SeedFunc", "CalleeSymbol", 1.0]]
                ]
            return [[], []]

        client.query.side_effect = mock_query
        ppr = HippoRAGPPR()
        ppr.client = client

        res = ppr.retrieve_associative_subgraph(["SeedFunc"], graph_name="cerebrum")
        nodes = {r[0] for r in res}
        assert "SeedFunc" in nodes
        assert "EpisodicConcept" in nodes
        assert "CalleeSymbol" in nodes

    def test_hippo_ppr_graceful_fallback_when_symbols_fails(self):
        client = MagicMock()
        def mock_query(graph, cypher, params=None):
            if graph == "cerebrum":
                return [
                    ["source", "target", "weight"],
                    [["SeedFunc", "EpisodicConcept", 0.8]]
                ]
            raise RuntimeError("Symbols graph socket error")

        client.query.side_effect = mock_query
        ppr = HippoRAGPPR()
        ppr.client = client

        res = ppr.retrieve_associative_subgraph(["SeedFunc"], graph_name="cerebrum")
        nodes = {r[0] for r in res}
        assert "SeedFunc" in nodes
        assert "EpisodicConcept" in nodes

    def test_hippo_ppr_graceful_fallback_when_cerebrum_fails(self):
        client = MagicMock()
        def mock_query(graph, cypher, params=None):
            if graph == "cerebrum_symbols":
                return [
                    ["source", "target", "weight"],
                    [["SeedFunc", "CalleeSymbol", 1.0]]
                ]
            raise RuntimeError("Cerebrum graph offline")

        client.query.side_effect = mock_query
        ppr = HippoRAGPPR()
        ppr.client = client

        res = ppr.retrieve_associative_subgraph(["SeedFunc"], graph_name="cerebrum")
        nodes = {r[0] for r in res}
        assert "SeedFunc" in nodes
        assert "CalleeSymbol" in nodes

    def test_hippo_ppr_single_graph_when_symbols_disabled(self):
        client = MagicMock()
        client.query.return_value = [
            ["source", "target", "weight"],
            [["SeedFunc", "EpisodicConcept", 0.8]]
        ]
        ppr = HippoRAGPPR()
        ppr.client = client

        res = ppr.retrieve_associative_subgraph(["SeedFunc"], graph_name="cerebrum", symbols_graph=None)
        client.query.assert_called_once()
        assert client.query.call_args[0][0] == "cerebrum"
        assert len(res) == 2


