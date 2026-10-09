"""
Tests for centralized zero-config embedding provider with FastEmbed fallback.

Covers:
1. DenseEmbedderProtocol / DenseEmbedder interface compliance.
2. Fallback to FastEmbed (BAAI/bge-small-en-v1.5, dimension 384) when EMBED_BASE_URL
   is offline, connection refused, or unset.
3. Correct dense vector generation for embed_documents([texts]) and embed_query(query).
4. Dimension property reporting 384 for FastEmbed and 4096 for remote mlx model.
5. Singleton caching of the FastEmbed model to avoid reload overhead.
"""

from __future__ import annotations

import os
from typing import List
from unittest.mock import MagicMock, patch

import httpx
import pytest

from kortext.embeddings import (
    DenseEmbedder,
    DenseEmbedderProtocol,
    EmbeddingConfig,
    EmbeddingError,
    FastEmbedDenseProvider,
    FastEmbedError,
    RemoteDenseProvider,
    RemoteEmbeddingError,
    get_dense_embedder,
    is_remote_embed_alive,
)


class TestProtocolCompliance:
    """Verifies interface adherence for all embedding providers."""

    def test_fastembed_implements_protocol(self):
        provider = FastEmbedDenseProvider()
        assert isinstance(provider, DenseEmbedder)
        assert isinstance(provider, DenseEmbedderProtocol)
        assert hasattr(provider, "dimension")
        assert hasattr(provider, "embed_documents")
        assert hasattr(provider, "embed_query")

    def test_remote_provider_implements_protocol(self):
        provider = RemoteDenseProvider(base_url="http://127.0.0.1:8000/v1")
        assert isinstance(provider, DenseEmbedder)
        assert isinstance(provider, DenseEmbedderProtocol)
        assert hasattr(provider, "dimension")
        assert hasattr(provider, "embed_documents")
        assert hasattr(provider, "embed_query")

    def test_invalid_class_fails_protocol_check(self):
        class NonEmbedder:
            pass

        assert not isinstance(NonEmbedder(), DenseEmbedder)


class TestDimensionProperties:
    """Verifies dimension reporting for both FastEmbed and Remote providers."""

    def test_fastembed_dimension_reports_384(self):
        provider = FastEmbedDenseProvider(model_name="BAAI/bge-small-en-v1.5")
        assert provider.dimension == 384

    def test_remote_mlx_model_dimension_reports_4096(self):
        provider = RemoteDenseProvider(
            base_url="http://127.0.0.1:8000/v1",
            model_name="mlx-community--Qwen3-Embedding-8B-4bit-DWQ",
        )
        assert provider.dimension == 4096

    def test_remote_provider_custom_dimension(self):
        provider = RemoteDenseProvider(
            base_url="http://127.0.0.1:8000/v1",
            model_name="custom-model",
            dimension=1024,
        )
        assert provider.dimension == 1024


class TestProbeAndFallback:
    """Verifies probe mechanism and fallback to FastEmbed."""

    def test_probe_returns_false_when_unset_or_empty(self, monkeypatch):
        monkeypatch.delenv("EMBED_BASE_URL", raising=False)
        monkeypatch.delenv("KORTEXT_EMBED_BASE_URL", raising=False)
        monkeypatch.delenv("CEREBRUM_EMBED_BASE_URL", raising=False)
        assert not is_remote_embed_alive("")
        assert not is_remote_embed_alive("none")

    def test_probe_returns_false_on_connection_refused(self):
        # Port 59999 is typically unused and refuses connection
        assert not is_remote_embed_alive("http://127.0.0.1:59999/v1", timeout=0.2)

    def test_probe_returns_true_when_server_responds(self):
        with patch("httpx.Client.get") as mock_get:
            mock_resp = MagicMock()
            mock_resp.status_code = 200
            mock_get.return_value = mock_resp
            assert is_remote_embed_alive("http://127.0.0.1:8000/v1")

    def test_get_dense_embedder_returns_remote_when_alive(self):
        with patch("kortext.embeddings.is_remote_embed_alive", return_value=True):
            embedder = get_dense_embedder(force_fastembed=False)
            assert isinstance(embedder, RemoteDenseProvider)
            assert embedder.dimension == 4096

    def test_get_dense_embedder_falls_back_when_offline(self):
        with patch("kortext.embeddings.is_remote_embed_alive", return_value=False):
            embedder = get_dense_embedder(force_fastembed=False)
            assert isinstance(embedder, FastEmbedDenseProvider)
            assert embedder.dimension == 384

    def test_get_dense_embedder_force_fastembed(self):
        with patch("kortext.embeddings.is_remote_embed_alive", return_value=True):
            embedder = get_dense_embedder(force_fastembed=True)
            assert isinstance(embedder, FastEmbedDenseProvider)
            assert embedder.dimension == 384


class TestFastEmbedVectorGeneration:
    """Verifies local FastEmbed vector computation."""

    def test_embed_documents_single_and_batch(self):
        provider = FastEmbedDenseProvider()
        texts = ["FastEmbed zero-config retrieval.", "Second sentence for batching."]
        vectors = provider.embed_documents(texts)

        assert len(vectors) == 2
        assert len(vectors[0]) == 384
        assert len(vectors[1]) == 384
        assert all(isinstance(x, float) for x in vectors[0])
        assert all(isinstance(x, float) for x in vectors[1])

    def test_embed_documents_empty_list(self):
        provider = FastEmbedDenseProvider()
        assert provider.embed_documents([]) == []

    def test_embed_query(self):
        provider = FastEmbedDenseProvider()
        query = "How to test embedding providers?"
        vector = provider.embed_query(query)

        assert isinstance(vector, list)
        assert len(vector) == 384
        assert all(isinstance(x, float) for x in vector)

    def test_embed_query_empty_string(self):
        provider = FastEmbedDenseProvider()
        vector = provider.embed_query("")
        assert len(vector) == 384


class TestRemoteProviderVectorGeneration:
    """Verifies RemoteDenseProvider HTTP handling, parsing, and retry logic."""

    def test_remote_embed_documents_success(self):
        mock_vec_1 = [0.1] * 4096
        mock_vec_2 = [0.2] * 4096

        def mock_post(url, **kwargs):
            resp = MagicMock()
            resp.status_code = 200
            resp.json.return_value = {
                "data": [
                    {"index": 0, "embedding": mock_vec_1},
                    {"index": 1, "embedding": mock_vec_2},
                ]
            }
            return resp

        with patch("httpx.Client.post", side_effect=mock_post):
            provider = RemoteDenseProvider(base_url="http://127.0.0.1:8000/v1")
            results = provider.embed_documents(["doc one", "doc two"])
            assert len(results) == 2
            assert results[0] == mock_vec_1
            assert results[1] == mock_vec_2

    def test_remote_embed_query_success(self):
        mock_vec = [0.42] * 4096

        def mock_post(url, **kwargs):
            resp = MagicMock()
            resp.status_code = 200
            resp.json.return_value = {
                "data": [{"index": 0, "embedding": mock_vec}]
            }
            return resp

        with patch("httpx.Client.post", side_effect=mock_post):
            provider = RemoteDenseProvider(base_url="http://127.0.0.1:8000/v1")
            res = provider.embed_query("test query")
            assert len(res) == 4096
            assert res == mock_vec

    def test_remote_empty_documents_no_network_call(self):
        provider = RemoteDenseProvider(base_url="http://127.0.0.1:8000/v1")
        with patch("httpx.Client.post") as mock_post:
            assert provider.embed_documents([]) == []
            mock_post.assert_not_called()

    def test_remote_retry_on_temporary_503(self):
        call_count = 0
        mock_vec = [0.5] * 4096

        def mock_post(url, **kwargs):
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                resp = MagicMock()
                resp.status_code = 503
                raise httpx.HTTPStatusError("Service Unavailable", request=MagicMock(), response=resp)
            resp = MagicMock()
            resp.status_code = 200
            resp.json.return_value = {
                "data": [{"index": 0, "embedding": mock_vec}]
            }
            return resp

        with patch("httpx.Client.post", side_effect=mock_post):
            provider = RemoteDenseProvider(base_url="http://127.0.0.1:8000/v1", max_retries=2)
            results = provider.embed_documents(["test"])
            assert len(results) == 1
            assert results[0] == mock_vec
            assert call_count == 2

    def test_remote_raises_after_retry_exhaustion(self):
        def mock_post(url, **kwargs):
            resp = MagicMock()
            resp.status_code = 500
            raise httpx.HTTPStatusError("Internal Server Error", request=MagicMock(), response=resp)

        with patch("httpx.Client.post", side_effect=mock_post):
            provider = RemoteDenseProvider(base_url="http://127.0.0.1:8000/v1", max_retries=2)
            with pytest.raises(RemoteEmbeddingError):
                provider.embed_documents(["test"])


class TestSingletonCaching:
    """Verifies that FastEmbed model instances are cached as singletons to avoid reloads."""

    def test_get_dense_embedder_returns_same_fastembed_instance(self):
        p1 = get_dense_embedder(force_fastembed=True)
        p2 = get_dense_embedder(force_fastembed=True)
        assert p1 is p2

    def test_fastembed_providers_share_underlying_model(self):
        p1 = FastEmbedDenseProvider(model_name="BAAI/bge-small-en-v1.5")
        p2 = FastEmbedDenseProvider(model_name="BAAI/bge-small-en-v1.5")
        # Underlying TextEmbedding object must be identical in memory
        assert p1.model is p2.model


class TestConfigurationImmutability:
    """Verifies frozen config dataclass immutability."""

    def test_embedding_config_is_frozen(self):
        cfg = EmbeddingConfig()
        with pytest.raises(AttributeError):
            cfg.remote_model_name = "different-model"  # type: ignore


class TestAsyncEmbeddingMethods:
    """Verifies asynchronous embedding methods for FastEmbed and Remote providers."""

    @pytest.mark.asyncio
    async def test_fastembed_async_methods(self):
        provider = FastEmbedDenseProvider()
        docs = ["Async document 1", "Async document 2"]
        doc_vecs = await provider.aembed_documents(docs)
        assert len(doc_vecs) == 2
        assert len(doc_vecs[0]) == 384

        q_vec = await provider.aembed_query("Async query")
        assert len(q_vec) == 384

    @pytest.mark.asyncio
    async def test_remote_async_methods(self):
        mock_vec = [0.7] * 4096

        def mock_post(url, **kwargs):
            resp = MagicMock()
            resp.status_code = 200
            resp.json.return_value = {
                "data": [{"index": 0, "embedding": mock_vec}]
            }
            return resp

        with patch("httpx.AsyncClient.post", side_effect=mock_post):
            provider = RemoteDenseProvider(base_url="http://127.0.0.1:8000/v1")
            doc_vecs = await provider.aembed_documents(["doc"])
            assert len(doc_vecs) == 1
            assert doc_vecs[0] == mock_vec

            q_vec = await provider.aembed_query("query")
            assert q_vec == mock_vec


class TestUnsetEnvFallback:
    """Verifies that get_dense_embedder falls back to FastEmbed when EMBED_BASE_URL is unset."""

    def test_fallback_when_env_unset(self, monkeypatch):
        monkeypatch.delenv("EMBED_BASE_URL", raising=False)
        monkeypatch.delenv("KORTEXT_EMBED_BASE_URL", raising=False)
        monkeypatch.delenv("CEREBRUM_EMBED_BASE_URL", raising=False)

        embedder = get_dense_embedder()
        assert isinstance(embedder, FastEmbedDenseProvider)
        assert embedder.dimension == 384

