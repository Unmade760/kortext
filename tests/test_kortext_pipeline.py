"""
Unit tests for Kortext native async pipeline (KortextPipeline) and make_graph factory.
"""

import asyncio
from unittest.mock import AsyncMock, MagicMock, patch
import pytest

from kortext.graph import (
    KortextPipeline,
    KortextState,
    CerebrumPipeline,
    CerebrumState,
    CortexState,
    make_graph,
    extract_symbol_candidates,
    _extract_symbol_candidates,
)


@pytest.mark.filterwarnings("ignore::DeprecationWarning")
@pytest.mark.anyio
async def test_make_graph_returns_kortext_pipeline():
    mock_retrieval = AsyncMock()
    mock_episodic = AsyncMock()
    mock_symbol_graph = MagicMock()

    pipeline = make_graph(
        retrieval=mock_retrieval,
        episodic=mock_episodic,
        symbol_graph=mock_symbol_graph,
    )
    assert isinstance(pipeline, KortextPipeline)
    assert pipeline.retrieval is mock_retrieval
    assert pipeline.episodic is mock_episodic
    assert pipeline.symbol_graph is mock_symbol_graph


@pytest.mark.filterwarnings("ignore::DeprecationWarning")
@pytest.mark.anyio
async def test_kortext_pipeline_default_symbol_graph():
    mock_retrieval = AsyncMock()
    mock_episodic = AsyncMock()

    with patch("kortext.graph.SymbolGraphManager") as mock_sym_mgr_cls:
        mock_instance = MagicMock()
        mock_sym_mgr_cls.return_value = mock_instance

        pipeline = KortextPipeline(
            retrieval=mock_retrieval,
            episodic=mock_episodic,
            symbol_graph=None,
        )
        assert pipeline.symbol_graph is mock_instance
        mock_sym_mgr_cls.assert_called_once()


@pytest.mark.filterwarnings("ignore::DeprecationWarning")
@pytest.mark.anyio
async def test_kortext_pipeline_ainvoke_flow():
    mock_retrieval = AsyncMock()
    mock_retrieval.query = AsyncMock(return_value=["def test_foo(): pass"])

    mock_episodic = AsyncMock()
    mock_episodic.search = AsyncMock(return_value=["Learned pattern X"])

    mock_symbol_graph = MagicMock()
    mock_symbol_graph.graph_name = "kortext_symbols"
    mock_symbol_graph.find_references.return_value = {
        "symbol": "test_foo",
        "definitions": [{"file_path": "kortext/foo.py", "line": 10, "kind": "function", "signature": "def test_foo():", "docstring": "A test func."}],
        "imports": [{"file_path": "kortext/bar.py", "line": 2, "module": "kortext.foo"}],
        "references": [{"file_path": "tests/test_foo.py", "line": 15, "kind": "call"}],
    }

    pipeline = KortextPipeline(
        retrieval=mock_retrieval,
        episodic=mock_episodic,
        symbol_graph=mock_symbol_graph,
    )

    state: KortextState = {
        "query": "Where is test_foo defined?",
        "collection": "kortext_codebase",
        "workspace_root": "/fake/workspace",
    }

    result = await pipeline.ainvoke(state)
    assert isinstance(result, dict)
    assert "final_context" in result
    final_context = result["final_context"]

    # Verify all 4 tiers are formatted
    assert "### Deterministic Code Symbols & Cross-File References (FalkorDB)" in final_context
    assert "test_foo" in final_context
    assert "### Operational Facts & Decisions (Graphiti)" in final_context
    assert "Learned pattern X" in final_context
    assert "### System Architecture Overview (OpenViking)" in final_context
    assert "_No structural context available._" in final_context
    assert "### Ground-Truth Code References (Qdrant Reranked)" in final_context
    assert "def test_foo(): pass" in final_context


@pytest.mark.filterwarnings("ignore::DeprecationWarning")
@pytest.mark.anyio
async def test_kortext_pipeline_graceful_degradation():
    """Verify that failure in retrieval nodes does not crash pipeline."""
    mock_retrieval = AsyncMock()
    mock_retrieval.query = AsyncMock(side_effect=RuntimeError("Qdrant offline"))

    mock_episodic = AsyncMock()
    mock_episodic.search = AsyncMock(side_effect=RuntimeError("Episodic offline"))

    mock_symbol_graph = MagicMock()
    mock_symbol_graph.graph_name = "kortext_symbols"
    mock_symbol_graph.find_references.side_effect = RuntimeError("FalkorDB offline")

    pipeline = KortextPipeline(
        retrieval=mock_retrieval,
        episodic=mock_episodic,
        symbol_graph=mock_symbol_graph,
    )

    state: KortextState = {
        "query": "Where is test_symbol?",
        "collection": "kortext_codebase",
    }

    result = await pipeline.ainvoke(state)
    assert "final_context" in result
    final_context = result["final_context"]
    assert "_No relevant operational facts found._" in final_context
    assert "_No structural context available._" in final_context
    assert "_No code references found._" in final_context


def test_kortext_state_backwards_compatibility():
    assert CortexState is KortextState
    assert CerebrumState is KortextState
    assert extract_symbol_candidates is not None
    assert _extract_symbol_candidates is not None


def test_graph_deprecation_notices():
    """Verify deprecation notices and warnings for kortext.graph components."""
    import warnings
    import kortext.graph as graph_mod

    # 1. Module docstring deprecation notice
    assert "deprecated" in (graph_mod.__doc__ or "").lower()
    assert "retrievalengine.federated_query" in (graph_mod.__doc__ or "").lower()

    # 2. Class and function docstrings mention deprecation
    assert "deprecated" in (KortextPipeline.__doc__ or "").lower()
    assert "deprecated" in (make_graph.__doc__ or "").lower()

    # 3. Executing make_graph issues DeprecationWarning
    mock_retrieval = AsyncMock()
    mock_episodic = AsyncMock()
    mock_symbol_graph = MagicMock()

    with pytest.deprecated_call():
        p = make_graph(
            retrieval=mock_retrieval,
            episodic=mock_episodic,
            symbol_graph=mock_symbol_graph,
        )
        assert isinstance(p, KortextPipeline)


def test_server_does_not_depend_on_graph_pipeline():
    """Verify server.py does not import make_graph or bind graph to lifespan."""
    import inspect
    import kortext.server as server_mod

    # server should not import make_graph
    assert not hasattr(server_mod, "make_graph")

    # Inspect lifespan source code to verify make_graph is unbound
    lifespan_source = inspect.getsource(server_mod.lifespan)
    assert "make_graph" not in lifespan_source
