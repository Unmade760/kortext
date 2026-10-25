"""
Unit tests for unified federated retrieval pipeline (RetrievalEngine.federated_query),
replacing the retired kortext.graph (KortextPipeline / make_graph) module.
"""

from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch
import inspect
import pytest

from kortext.retrieval import RetrievalEngine, federated_query
from kortext.symbols.seek import extract_symbol_candidates, _extract_symbol_candidates


@pytest.mark.anyio
async def test_federated_query_executes_all_tiers():
    engine = RetrievalEngine()

    with patch("kortext.retrieval.engine.execute_federated_query", new_callable=AsyncMock) as mock_exec:
        mock_exec.return_value = {
            "query": "Where is test_foo defined?",
            "symbolic_context": [
                {
                    "symbol": "test_foo",
                    "kind": "function",
                    "file": "kortext/foo.py",
                    "lines": [10],
                    "signature": "def test_foo():",
                }
            ],
            "code_chunks": ["def test_foo(): pass"],
            "episodic_history": ["Learned pattern X"],
            "architectural_overview": "# Architecture Overview",
            "total_estimated_tokens": 120,
        }

        result = await engine.federated_query(
            query="Where is test_foo defined?",
            collection="kortext_codebase",
            workspace_root="/fake/workspace",
            token_budget=1500,
        )

        assert isinstance(result, dict)
        assert result["query"] == "Where is test_foo defined?"
        assert len(result["symbolic_context"]) == 1
        assert result["symbolic_context"][0]["symbol"] == "test_foo"
        assert "def test_foo(): pass" in result["code_chunks"]
        assert "Learned pattern X" in result["episodic_history"]
        assert result["architectural_overview"] == "# Architecture Overview"


@pytest.mark.anyio
async def test_module_level_federated_query_convenience_wrapper():
    mock_engine = MagicMock()
    mock_engine.federated_query = AsyncMock(
        return_value={
            "query": "test_symbol",
            "symbolic_context": [],
            "code_chunks": [],
            "episodic_history": [],
            "architectural_overview": None,
            "total_estimated_tokens": 0,
        }
    )

    res = await federated_query(
        query="test_symbol",
        token_budget=900,
        collection="kortext_codebase",
        engine=mock_engine,
    )
    assert res["query"] == "test_symbol"
    mock_engine.federated_query.assert_awaited_once_with(
        query="test_symbol",
        token_budget=900,
        collection="kortext_codebase",
        workspace_root=None,
        detail_level="balanced",
        project=None,
    )


def test_symbol_candidate_extractors_exported():
    assert extract_symbol_candidates is not None
    assert _extract_symbol_candidates is not None
    cands = extract_symbol_candidates("Where is RetrievalEngine.federated_query defined?")
    assert any("RetrievalEngine" in c or "federated_query" in c for c in cands)


def test_deprecated_graph_module_removed():
    """Verify dead kortext/graph.py module has been removed per audit remediation."""
    graph_file = Path(__file__).resolve().parent.parent / "kortext" / "graph.py"
    assert not graph_file.exists(), "Deprecated kortext/graph.py should be deleted"


def test_server_does_not_depend_on_graph_pipeline():
    """Verify server.py does not import make_graph or bind graph to lifespan."""
    import kortext.server as server_mod

    assert not hasattr(server_mod, "make_graph")
    lifespan_source = inspect.getsource(server_mod.lifespan)
    assert "make_graph" not in lifespan_source
