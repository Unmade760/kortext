"""
Unit tests for EmbeddedQdrantEngine using temporary local directories.
Verifies modern query_points API, named multi-vectors, and hybrid fusion.
"""

import tempfile
from unittest.mock import AsyncMock, patch
import pytest
from pathlib import Path
from qdrant_client.models import PointStruct
from kortext.retrieval.qdrant_engine import EmbeddedQdrantEngine


class TestEmbeddedQdrant:
    @pytest.fixture
    def qdrant_engine(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            engine = EmbeddedQdrantEngine(storage_path=Path(tmpdir))
            yield engine

    def test_dual_vector_collection_creation(self, qdrant_engine):
        col_name = "test_cerebrum_collection"
        qdrant_engine.ensure_collection(col_name, embed_dim=4)

        assert qdrant_engine.client.collection_exists(col_name)
        info = qdrant_engine.client.get_collection(col_name)
        
        # Verify named dense vector configuration
        assert "text-dense" in info.config.params.vectors
        assert info.config.params.vectors["text-dense"].size == 4
        # Verify named sparse vector configuration
        assert info.config.params.sparse_vectors is not None
        assert "text-sparse-new" in info.config.params.sparse_vectors

    def test_upsert_and_hybrid_query_points(self, qdrant_engine):
        col_name = "test_search_collection"
        qdrant_engine.ensure_collection(col_name, embed_dim=4)

        # Upsert point with dense and sparse components
        points = [
            PointStruct(
                id=1,
                vector={
                    "text-dense": [0.1, 0.2, 0.3, 0.4],
                    "text-sparse-new": {"indices": [10, 20], "values": [0.5, 0.8]}
                },
                payload={"title": "SessionManager Documentation", "lang": "python"}
            ),
            PointStruct(
                id=2,
                vector={
                    "text-dense": [0.9, 0.8, 0.7, 0.6],
                    "text-sparse-new": {"indices": [30], "values": [0.9]}
                },
                payload={"title": "FalkorDB Client Guide", "lang": "python"}
            )
        ]
        qdrant_engine.upsert_points(col_name, points)

        # Execute modern hybrid search using query_points with Prefetch
        results = qdrant_engine.hybrid_search(
            collection_name=col_name,
            dense_vector=[0.1, 0.2, 0.3, 0.4],
            sparse_indices=[10, 20],
            sparse_values=[0.5, 0.8],
            limit=1
        )

        assert len(results) == 1
        assert results[0]["id"] == 1
        assert results[0]["payload"]["title"] == "SessionManager Documentation"


@pytest.mark.anyio
async def test_resolve_workspace_root_embedded_mode(monkeypatch):
    """In native embedded mode (QDRANT_URL unset/empty), AsyncQdrantClient is not instantiated."""
    monkeypatch.delenv("QDRANT_URL", raising=False)
    from kortext.retrieval.engine import _COLLECTION_WORKSPACE_CACHE, resolve_workspace_root_for_collection

    _COLLECTION_WORKSPACE_CACHE.clear()

    with patch("qdrant_client.AsyncQdrantClient") as mock_async_client:
        res = await resolve_workspace_root_for_collection("unknown_embedded_collection_123")
        # Ensure network client is not instantiated
        mock_async_client.assert_not_called()
        assert res is not None


@pytest.mark.anyio
async def test_resolve_workspace_root_remote_mode(monkeypatch):
    """When QDRANT_URL is set, AsyncQdrantClient is instantiated."""
    monkeypatch.setenv("QDRANT_URL", "http://qdrant-host:6333")
    from kortext.retrieval.engine import _COLLECTION_WORKSPACE_CACHE, resolve_workspace_root_for_collection

    _COLLECTION_WORKSPACE_CACHE.clear()

    with patch("qdrant_client.AsyncQdrantClient") as mock_async_client:
        mock_inst = AsyncMock()
        mock_inst.scroll.return_value = ([], None)
        mock_async_client.return_value = mock_inst

        res = await resolve_workspace_root_for_collection("remote_collection_xyz")
        mock_async_client.assert_called_once_with(url="http://qdrant-host:6333")
        assert res is not None

