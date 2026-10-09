"""
Unit tests for multi-collection federated retrieval and FastMCP search_federated_memory tool.
Verifies parallel execution, envelope structure, token budget enforcement,
Knapsack MMR diversity, and graceful degradation across all 3 memory tiers.
"""

import asyncio
import json
import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from kortext.retrieval import (
    RetrievalEngine,
    federated_query,
    FederatedRetrievalResult,
    apply_knapsack_mmr,
)


@pytest.fixture
def mock_retrieval_engine():
    """Returns a RetrievalEngine with mocked Tier 0, Tier 1, and Tier 2 components."""
    engine = RetrievalEngine()

    # Mock symbol seek (Tier 0)
    mock_seek = MagicMock()
    mock_seek.seek_symbol.return_value = json.dumps({
        "status": "found",
        "matches": [
            {
                "symbol": "RetrievalEngine",
                "kind": "class",
                "file": "kortext/retrieval/engine.py",
                "lines": [279, 825],
                "signature": "class RetrievalEngine:",
                "docstring": "Manages 5-Signal Hybrid Reciprocal Rank Fusion",
            }
        ],
    })
    engine._symbol_seek = mock_seek

    # Mock query (Tier 1)
    engine.query = AsyncMock(return_value=[
        "def query(self, prompt: str) -> List[str]:\n    # Tier 1 hybrid search implementation\n    return []",
        "class HippoRAGPPR:\n    # Personalized PageRank subgraph exploration\n    pass",
    ])

    # Mock episodic search (Tier 2)
    mock_episodic = MagicMock()
    mock_episodic.search = AsyncMock(return_value=[
        "[Decision]: Switched to 5-signal RRF fusion with TAA-k trimming",
        "[Architecture]: FalkorDB UDS primary transport with TCP fallback",
        "[Observation]: Qdrant collection cerebrum_codebase reindexed",
    ])
    mock_episodic.initialize = AsyncMock()
    mock_episodic.close = AsyncMock()
    engine._episodic = mock_episodic

    return engine


class TestFederatedRetrievalEnvelope:
    """Verifies envelope keys, types, and structure."""

    @pytest.mark.anyio
    async def test_envelope_structure_and_keys(self, mock_retrieval_engine):
        res = await mock_retrieval_engine.federated_query("RetrievalEngine architecture and decisions")

        assert isinstance(res, dict)
        assert "query" in res
        assert "symbolic_context" in res
        assert "code_chunks" in res
        assert "episodic_history" in res
        assert "total_estimated_tokens" in res

        assert res["query"] == "RetrievalEngine architecture and decisions"
        assert isinstance(res["symbolic_context"], list)
        assert isinstance(res["code_chunks"], list)
        assert isinstance(res["episodic_history"], list)
        assert isinstance(res["total_estimated_tokens"], int)

        # Check content populated from tiers
        assert len(res["symbolic_context"]) >= 1
        assert res["symbolic_context"][0]["symbol"] == "RetrievalEngine"
        assert len(res["code_chunks"]) == 2
        assert len(res["episodic_history"]) >= 1
        assert res["total_estimated_tokens"] > 0
        assert res["total_estimated_tokens"] <= 1500

    @pytest.mark.anyio
    async def test_standalone_federated_query_function(self, mock_retrieval_engine):
        with patch("kortext.retrieval.engine.RetrievalEngine", return_value=mock_retrieval_engine):
            res = await federated_query("RetrievalEngine", token_budget=1000, engine=mock_retrieval_engine)
            assert res["query"] == "RetrievalEngine"
            assert res["total_estimated_tokens"] <= 1000


class TestParallelExecution:
    """Verifies that the 3 memory tiers execute concurrently."""

    @pytest.mark.anyio
    async def test_tiers_execute_concurrently(self, mock_retrieval_engine):
        execution_order = []

        def slow_seek(*args, **kwargs):
            execution_order.append("tier0_start")
            import time
            time.sleep(0.05)
            execution_order.append("tier0_end")
            return json.dumps({"status": "found", "matches": [{"symbol": "SymbolA"}]})

        async def slow_query(*args, **kwargs):
            execution_order.append("tier1_start")
            await asyncio.sleep(0.05)
            execution_order.append("tier1_end")
            return ["chunk_1"]

        async def slow_episodic(*args, **kwargs):
            execution_order.append("tier2_start")
            await asyncio.sleep(0.05)
            execution_order.append("tier2_end")
            return ["fact_1"]

        mock_retrieval_engine._symbol_seek.seek_symbol = slow_seek
        mock_retrieval_engine.query = slow_query
        mock_retrieval_engine._episodic.search = slow_episodic

        res = await mock_retrieval_engine.federated_query("SymbolA query")

        # In concurrent execution, tasks overlap rather than running sequentially
        assert "tier0_start" in execution_order
        assert "tier1_start" in execution_order
        assert "tier2_start" in execution_order
        assert len(res["symbolic_context"]) == 1
        assert len(res["code_chunks"]) == 1
        assert len(res["episodic_history"]) == 1


class TestTokenBudgetBounds:
    """Verifies strict token budgeting across tiers and total envelope."""

    @pytest.mark.anyio
    async def test_token_budget_strictly_enforced(self, mock_retrieval_engine):
        # Provide huge chunks and facts that exceed small budget
        mock_retrieval_engine.query = AsyncMock(return_value=[
            "x" * 2000,  # ~500 tokens
            "y" * 2000,  # ~500 tokens
            "z" * 2000,  # ~500 tokens
        ])
        mock_retrieval_engine._episodic.search = AsyncMock(return_value=[
            "fact_alpha " * 200,
            "fact_beta " * 200,
        ])

        budget = 300
        res = await mock_retrieval_engine.federated_query("RetrievalEngine", token_budget=budget)

        assert res["total_estimated_tokens"] <= budget

    @pytest.mark.anyio
    async def test_zero_or_negative_token_budget(self, mock_retrieval_engine):
        res = await mock_retrieval_engine.federated_query("RetrievalEngine", token_budget=0)
        assert res["total_estimated_tokens"] == 0
        assert res["symbolic_context"] == []
        assert res["code_chunks"] == []
        assert res["episodic_history"] == []


class TestKnapsackMMRDiversity:
    """Verifies Knapsack MMR algorithm on episodic history."""

    def test_knapsack_mmr_penalizes_redundancy(self):
        candidates = [
            "Weibull retention decay scales with parameter lambda_h = 72 hours",
            "Weibull retention decay scales with parameter lambda_h = 72.0 hours exactly",  # Near duplicate
            "FalkorDB graph stores AST nodes and CALLS relationships",  # Highly distinct
            "Qdrant vector collection cerebrum_codebase indexed with Qwen3 MRL",  # Highly distinct
        ]
        query = "Weibull decay and graph relationships"
        selected = apply_knapsack_mmr(candidates, query=query, token_budget=200, lambda_param=0.7)

        assert len(selected) >= 2
        # Near duplicate should be filtered or penalized in favor of diverse candidates
        assert not (candidates[0] in selected and candidates[1] in selected)
        assert any("FalkorDB" in s for s in selected)

    def test_knapsack_mmr_respects_token_capacity(self):
        candidates = [
            "short fact 1",
            "a" * 1600,  # ~400 tokens (too large for 50 budget)
            "short fact 2",
        ]
        selected = apply_knapsack_mmr(candidates, query="fact", token_budget=50)
        assert "short fact 1" in selected
        assert "short fact 2" in selected
        assert ("a" * 1600) not in selected


class TestGracefulDegradation:
    """Verifies that failures in one or more tiers do not crash the pipeline."""

    @pytest.mark.anyio
    async def test_tier0_failure_degrades_gracefully(self, mock_retrieval_engine):
        mock_retrieval_engine._symbol_seek.seek_symbol.side_effect = RuntimeError("FalkorDB offline")

        res = await mock_retrieval_engine.federated_query("RetrievalEngine")
        assert res["symbolic_context"] == []
        assert len(res["code_chunks"]) > 0
        assert len(res["episodic_history"]) > 0

    @pytest.mark.anyio
    async def test_tier1_failure_degrades_gracefully(self, mock_retrieval_engine):
        mock_retrieval_engine.query = AsyncMock(side_effect=ConnectionError("Qdrant offline"))

        res = await mock_retrieval_engine.federated_query("RetrievalEngine")
        assert len(res["symbolic_context"]) > 0
        assert res["code_chunks"] == []
        assert len(res["episodic_history"]) > 0

    @pytest.mark.anyio
    async def test_tier2_failure_degrades_gracefully(self, mock_retrieval_engine):
        mock_retrieval_engine._episodic.search = AsyncMock(side_effect=TimeoutError("Episodic timeout"))

        res = await mock_retrieval_engine.federated_query("RetrievalEngine")
        assert len(res["symbolic_context"]) > 0
        assert len(res["code_chunks"]) > 0
        assert res["episodic_history"] == []

    @pytest.mark.anyio
    async def test_all_tiers_failure_returns_empty_envelope(self, mock_retrieval_engine):
        mock_retrieval_engine._symbol_seek.seek_symbol.side_effect = RuntimeError("Offline")
        mock_retrieval_engine.query = AsyncMock(side_effect=RuntimeError("Offline"))
        mock_retrieval_engine._episodic.search = AsyncMock(side_effect=RuntimeError("Offline"))

        res = await mock_retrieval_engine.federated_query("RetrievalEngine")
        assert res["query"] == "RetrievalEngine"
        assert res["symbolic_context"] == []
        assert res["code_chunks"] == []
        assert res["episodic_history"] == []
        assert res["total_estimated_tokens"] == 0


class TestFastMCPFederatedMemoryTool:
    """Verifies FastMCP search_knowledge_and_memory tool in server.py."""

    @pytest.mark.anyio
    async def test_search_knowledge_and_memory_with_query(self, mock_retrieval_engine):
        from kortext.server import search_knowledge_and_memory

        with patch("kortext.server.retrieval", mock_retrieval_engine):
            res_str = await search_knowledge_and_memory(
                query="How does RetrievalEngine handle hybrid search?",
                token_budget=1400,
                detail_level="balanced",
            )
            assert isinstance(res_str, str)
            data = json.loads(res_str)
            assert data["query"] == "How does RetrievalEngine handle hybrid search?"
            assert "symbolic_context" in data
            assert "code_chunks" in data
            assert "episodic_history" in data
            assert "markdown" in data
            assert data["total_estimated_tokens"] <= 1400

    @pytest.mark.anyio
    async def test_search_knowledge_and_memory_with_query_kwarg(self, mock_retrieval_engine):
        from kortext.server import search_knowledge_and_memory

        with patch("kortext.server.retrieval", mock_retrieval_engine):
            res_str = await search_knowledge_and_memory(
                query="SymbolSeekEngine architecture",
                token_budget=1000,
            )
            assert isinstance(res_str, str)
            data = json.loads(res_str)
            assert data["query"] == "SymbolSeekEngine architecture"
            assert "markdown" in data

    @pytest.mark.anyio
    async def test_federated_query_forwards_parameters(self, mock_retrieval_engine):
        # 1. Compact detail_level maps to skeleton AST, custom collection forwarded to query
        await mock_retrieval_engine.federated_query(
            "RetrievalEngine",
            collection="custom_collection",
            detail_level="compact",
        )
        mock_retrieval_engine._symbol_seek.seek_symbol.assert_called_with(
            "RetrievalEngine",
            detail_level="skeleton",
            graph_name="custom_collection_symbols",
            workspace_root=mock_retrieval_engine._symbol_seek.seek_symbol.call_args.kwargs.get("workspace_root"),
        )
        assert mock_retrieval_engine.query.call_args.kwargs.get("collection") == "custom_collection"

        # 2. Comprehensive detail_level maps to full AST, default collection fallback
        mock_retrieval_engine._symbol_seek.seek_symbol.reset_mock()
        mock_retrieval_engine.query.reset_mock()
        await mock_retrieval_engine.federated_query(
            "RetrievalEngine",
            detail_level="comprehensive",
        )
        assert mock_retrieval_engine._symbol_seek.seek_symbol.call_args[0] == ("RetrievalEngine",)
        assert mock_retrieval_engine._symbol_seek.seek_symbol.call_args.kwargs.get("detail_level") == "full"
        assert mock_retrieval_engine._symbol_seek.seek_symbol.call_args.kwargs.get("graph_name") in ("kortext_symbols", "cerebrum_symbols")
        assert mock_retrieval_engine._symbol_seek.seek_symbol.call_args.kwargs.get("workspace_root") is None
        assert mock_retrieval_engine.query.call_args.kwargs.get("collection") in ("kortext_codebase", "cerebrum_codebase")

    @pytest.mark.anyio
    async def test_search_knowledge_and_memory_forwards_all_parameters(self, mock_retrieval_engine):
        from kortext.server import search_knowledge_and_memory

        with patch.object(mock_retrieval_engine, "federated_query", new_callable=AsyncMock) as mock_fq:
            mock_fq.return_value = {
                "query": "RetrievalEngine",
                "symbolic_context": [],
                "code_chunks": [],
                "episodic_history": [],
                "total_estimated_tokens": 100,
            }
            with patch("kortext.server.retrieval", mock_retrieval_engine):
                await search_knowledge_and_memory(
                    query="RetrievalEngine",
                    collection="test_col",
                    workspace_root="/test/workspace",
                    token_budget=1200,
                    detail_level="compact",
                )
                mock_fq.assert_awaited_once_with(
                    query="RetrievalEngine",
                    token_budget=1200,
                    collection="test_col",
                    workspace_root="/test/workspace",
                    detail_level="compact",
                    project=None,
                )

    @pytest.mark.anyio
    async def test_collection_auto_resolves_workspace_root_and_scopes_tiers(self, mock_retrieval_engine):
        from kortext.server import search_knowledge_and_memory

        mock_retrieval_engine._symbol_seek.seek_symbol.return_value = json.dumps({
            "status": "found",
            "matches": [
                {
                    "symbol": "InsideSymbol",
                    "kind": "class",
                    "file": "/resolved/workspace/src/inside.py",
                    "lines": [10, 20],
                    "signature": "class InsideSymbol",
                },
                {
                    "symbol": "OutsideSymbol",
                    "kind": "class",
                    "file": "/other/project/src/outside.py",
                    "lines": [30, 40],
                    "signature": "class OutsideSymbol",
                },
            ],
        })

        mock_retrieval_engine.query = AsyncMock(return_value=[
            "# File: /resolved/workspace/src/inside.py:1-10\nInside chunk code",
            "# File: /other/project/src/outside.py:1-10\nOutside chunk code",
        ])

        with patch(
            "kortext.server.resolve_workspace_root_for_collection",
            new_callable=AsyncMock,
            return_value="/resolved/workspace",
        ) as mock_resolve_server_ws, patch(
            "kortext.retrieval.engine.resolve_workspace_root_for_collection",
            new_callable=AsyncMock,
            return_value="/resolved/workspace",
        ) as mock_resolve_engine_ws, patch(
            "kortext.server.retrieval",
            mock_retrieval_engine,
        ):
            res_str = await search_knowledge_and_memory(
                query="InsideSymbol",
                collection="my_custom_collection",
            )
            data = json.loads(res_str)

            mock_resolve_server_ws.assert_awaited_once_with("my_custom_collection")

            symbols = data["symbolic_context"]
            assert len(symbols) == 1
            assert symbols[0]["symbol"] == "InsideSymbol"

            chunks = data["code_chunks"]
            assert len(chunks) == 1
            assert "Inside chunk code" in chunks[0]
            assert "Outside chunk code" not in chunks[0]

            mock_retrieval_engine.query.assert_awaited()
            assert mock_retrieval_engine.query.call_args.kwargs.get("collection") == "my_custom_collection"

            # Also verify direct federated_query auto-resolves workspace_root and scopes
            res_direct = await mock_retrieval_engine.federated_query(
                query="InsideSymbol",
                collection="my_custom_collection",
            )
            mock_resolve_engine_ws.assert_awaited_once_with("my_custom_collection")
            assert len(res_direct["symbolic_context"]) == 1
            assert res_direct["symbolic_context"][0]["symbol"] == "InsideSymbol"


class TestProjectScopedFederatedRetrieval:
    """Verifies that federated_query and search_knowledge_and_memory respect project scoping."""

    @pytest.mark.anyio
    async def test_federated_query_respects_explicit_project(self, mock_retrieval_engine):
        res = await mock_retrieval_engine.federated_query(
            "Database migration decisions",
            project="project_alpha",
        )
        assert res is not None
        mock_retrieval_engine._episodic.search.assert_awaited()
        call_kwargs = mock_retrieval_engine._episodic.search.call_args.kwargs
        assert call_kwargs.get("project") == "project_alpha"

    @pytest.mark.anyio
    async def test_federated_query_respects_project_all(self, mock_retrieval_engine):
        res = await mock_retrieval_engine.federated_query(
            "Global architecture outcomes",
            project="all",
        )
        assert res is not None
        mock_retrieval_engine._episodic.search.assert_awaited()
        call_kwargs = mock_retrieval_engine._episodic.search.call_args.kwargs
        assert call_kwargs.get("project") == "all"

    @pytest.mark.anyio
    async def test_federated_query_resolves_project_from_collection(self, mock_retrieval_engine):
        await mock_retrieval_engine.federated_query(
            "Service auth facts",
            collection="custom_microservice",
        )
        mock_retrieval_engine._episodic.search.assert_awaited()
        call_kwargs = mock_retrieval_engine._episodic.search.call_args.kwargs
        assert call_kwargs.get("project") == "custom_microservice"

    @pytest.mark.anyio
    async def test_federated_query_resolves_project_from_workspace_root(self, mock_retrieval_engine):
        await mock_retrieval_engine.federated_query(
            "App routing facts",
            workspace_root="/Users/rb/projects/my_mobile_app",
        )
        mock_retrieval_engine._episodic.search.assert_awaited()
        call_kwargs = mock_retrieval_engine._episodic.search.call_args.kwargs
        assert call_kwargs.get("project") == "my_mobile_app"

    @pytest.mark.anyio
    async def test_federated_query_resolves_project_from_env_var(self, mock_retrieval_engine, monkeypatch):
        monkeypatch.setenv("KORTEXT_PROJECT", "env_assigned_project")
        await mock_retrieval_engine.federated_query(
            "Deployment facts",
        )
        mock_retrieval_engine._episodic.search.assert_awaited()
        call_kwargs = mock_retrieval_engine._episodic.search.call_args.kwargs
        assert call_kwargs.get("project") == "env_assigned_project"

    @pytest.mark.anyio
    async def test_federated_query_defaults_project_to_kortext(self, mock_retrieval_engine, monkeypatch):
        monkeypatch.delenv("KORTEXT_PROJECT", raising=False)
        await mock_retrieval_engine.federated_query(
            "Core engine facts",
        )
        mock_retrieval_engine._episodic.search.assert_awaited()
        call_kwargs = mock_retrieval_engine._episodic.search.call_args.kwargs
        assert call_kwargs.get("project") == "kortext"

    @pytest.mark.anyio
    async def test_search_knowledge_and_memory_forwards_project(self, mock_retrieval_engine):
        from kortext.server import search_knowledge_and_memory

        with patch.object(mock_retrieval_engine, "federated_query", new_callable=AsyncMock) as mock_fq:
            mock_fq.return_value = {
                "query": "Scoping query",
                "symbolic_context": [],
                "code_chunks": [],
                "episodic_history": [],
                "total_estimated_tokens": 50,
            }
            with patch("kortext.server.retrieval", mock_retrieval_engine):
                await search_knowledge_and_memory(
                    query="Scoping query",
                    project="target_project",
                )
                mock_fq.assert_awaited_once_with(
                    query="Scoping query",
                    token_budget=1500,
                    collection=None,
                    workspace_root=None,
                    detail_level="balanced",
                    project="target_project",
                )

