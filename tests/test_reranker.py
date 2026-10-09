"""
Unit tests for RerankerEngine with online scoring and offline fallback.
"""

import asyncio
from unittest.mock import AsyncMock, MagicMock, patch
import httpx
import pytest

from kortext.retrieval.reranker import RerankerEngine, compute_offline_score


class TestRerankerEngine:
    def test_empty_candidates_returns_empty_list(self):
        async def _run():
            engine = RerankerEngine()
            assert await engine.rerank("query", []) == []
            await engine.close()

        asyncio.run(_run())

    def test_top_k_limit(self):
        async def _run():
            engine = RerankerEngine()
            candidates = [{"text": f"doc {i}", "score": 0.01 * i} for i in range(10)]
            results = await engine.rerank("query", candidates, top_k=3)
            assert len(results) == 3
            await engine.close()

        asyncio.run(_run())

    def test_offline_fallback_deterministic_scoring(self, monkeypatch):
        """Verifies deterministic lexical tie-breaking: token matches + AST header/signature bonus."""
        monkeypatch.setenv("CEREBRUM_CI_MODE", "1")

        async def _run():
            engine = RerankerEngine()

            query = "def calculate_loss"

            cand_ast = {
                "text": "### AST Symbol: `calculate_loss` (function)\n- File: `loss.py`\n- Signature: `def calculate_loss(pred, target):`\nDocstring: computes loss",
                "score": 0.02,
            }
            cand_low_match = {
                "text": "Unrelated documentation about loss calculations.",
                "score": 0.02,
            }
            cand_high_match_no_ast = {
                "text": "Here we call def calculate_loss twice: calculate_loss(a, b) and calculate_loss(c, d).",
                "score": 0.02,
            }

            results = await engine.rerank(query, [cand_low_match, cand_high_match_no_ast, cand_ast], top_k=3)

            assert len(results) == 3
            # AST match with signature should rank highest due to AST bonus + token matches
            assert results[0]["text"] == cand_ast["text"]
            assert results[0]["rerank_score"] > results[1]["rerank_score"]
            # High token match should rank above low match
            assert results[1]["text"] == cand_high_match_no_ast["text"]
            assert results[2]["text"] == cand_low_match["text"]
            await engine.close()

        asyncio.run(_run())

    def test_offline_fallback_signature_bonus(self):
        """Verifies compute_offline_score awards bonus for AST headers and signature matches."""
        query = "find_symbol"
        cand_with_sig = {
            "text": "### AST Symbol: `find_symbol`\n- Signature: `def find_symbol(name: str):`",
            "score": 0.01,
        }
        cand_without_sig = {
            "text": "Mentions find_symbol in a comment",
            "score": 0.01,
        }

        score_sig = compute_offline_score(query, cand_with_sig)
        score_no_sig = compute_offline_score(query, cand_without_sig)

        assert score_sig > score_no_sig

    def test_online_scoring_success(self, monkeypatch):
        """Verifies successful HTTP 200 response from cross-encoder reranks candidates."""
        monkeypatch.delenv("CEREBRUM_CI_MODE", raising=False)
        monkeypatch.delenv("KORTEXT_CI_MODE", raising=False)

        async def _run():
            engine = RerankerEngine(base_url="http://127.0.0.1:8000/v1")

            query = "database connection"
            candidates = [
                {"text": "doc A about redis", "score": 0.05},
                {"text": "doc B about postgres connection pool", "score": 0.02},
            ]

            mock_response = MagicMock()
            mock_response.status_code = 200
            mock_response.raise_for_status = MagicMock()
            mock_response.json.return_value = {
                "results": [
                    {"index": 0, "relevance_score": 0.15},
                    {"index": 1, "relevance_score": 0.95},
                ]
            }

            with patch.object(httpx.AsyncClient, "post", AsyncMock(return_value=mock_response)) as mock_post:
                results = await engine.rerank(query, candidates, top_k=2)
                mock_post.assert_called_once()
                # Doc B had higher cross-encoder relevance score (0.95 vs 0.15)
                assert results[0]["text"] == "doc B about postgres connection pool"
                assert results[0]["rerank_score"] == 0.95
                assert results[1]["text"] == "doc A about redis"
                assert results[1]["rerank_score"] == 0.15
            await engine.close()

        asyncio.run(_run())

    def test_online_timeout_falls_back_to_offline(self, monkeypatch):
        """Verifies strict 250ms timeout triggers graceful fallback to offline scoring."""
        monkeypatch.delenv("CEREBRUM_CI_MODE", raising=False)
        monkeypatch.delenv("KORTEXT_CI_MODE", raising=False)

        async def _run():
            engine = RerankerEngine(base_url="http://127.0.0.1:8000/v1")

            query = "test timeout"
            candidates = [
                {"text": "doc with test timeout token match", "score": 0.01},
                {"text": "unrelated content", "score": 0.01},
            ]

            with patch.object(httpx.AsyncClient, "post", AsyncMock(side_effect=httpx.TimeoutException("Read timed out"))):
                results = await engine.rerank(query, candidates, top_k=2)
                assert len(results) == 2
                # Should have fallen back to lexical tie-breaker where first doc has token matches
                assert results[0]["text"] == "doc with test timeout token match"
                assert results[0]["rerank_score"] > results[1]["rerank_score"]
            await engine.close()

        asyncio.run(_run())

    def test_online_http_error_falls_back_to_offline(self, monkeypatch):
        """Verifies 500 server error triggers graceful fallback to offline scoring."""
        monkeypatch.delenv("CEREBRUM_CI_MODE", raising=False)
        monkeypatch.delenv("KORTEXT_CI_MODE", raising=False)

        async def _run():
            engine = RerankerEngine(base_url="http://127.0.0.1:8000/v1")

            query = "server error handling"
            candidates = [
                {"text": "server error handling doc", "score": 0.02},
                {"text": "other document", "score": 0.02},
            ]

            mock_response = MagicMock()
            mock_response.status_code = 500
            mock_response.raise_for_status.side_effect = httpx.HTTPStatusError(
                "Internal Server Error", request=MagicMock(), response=mock_response
            )

            with patch.object(httpx.AsyncClient, "post", AsyncMock(return_value=mock_response)):
                results = await engine.rerank(query, candidates, top_k=2)
                assert len(results) == 2
                assert results[0]["text"] == "server error handling doc"
            await engine.close()

        asyncio.run(_run())

    def test_candidate_format_variations(self, monkeypatch):
        """Verifies reranker supports strings and dicts with different text keys."""
        monkeypatch.setenv("CEREBRUM_CI_MODE", "1")

        async def _run():
            engine = RerankerEngine()

            candidates = [
                {"passage": "passage content for test", "score": 0.01},
                {"document": "document content for test", "score": 0.01},
                "raw string content for test",
            ]

            results = await engine.rerank("test", candidates, top_k=3)
            assert len(results) == 3
            for item in results:
                assert isinstance(item, dict)
                assert "text" in item
                assert "rerank_score" in item
            await engine.close()

        asyncio.run(_run())

    def test_rerank_sync_wrapper(self, monkeypatch):
        """Verifies synchronous rerank_sync wrapper executes offline fallback correctly."""
        monkeypatch.setenv("CEREBRUM_CI_MODE", "1")
        engine = RerankerEngine()
        candidates = [
            {"text": "match query token", "score": 0.01},
            {"text": "unrelated", "score": 0.01},
        ]
        results = engine.rerank_sync("query", candidates, top_k=2)
        assert len(results) == 2
        assert results[0]["text"] == "match query token"

    def test_close_cleans_up_client(self):
        """Verifies close() closes and nulls out the active AsyncClient."""
        async def _run():
            engine = RerankerEngine()
            client = engine._get_client()
            assert not client.is_closed
            assert engine._client is not None
            await engine.close()
            assert engine._client is None
            assert client.is_closed

        asyncio.run(_run())

    def test_retrieval_engine_reranker_integration(self):
        """Verifies RetrievalEngine initializes RerankerEngine and invokes it post-TAA-k."""
        from kortext.retrieval.engine import RetrievalEngine

        engine = RetrievalEngine()
        assert isinstance(engine.reranker, RerankerEngine)

        async def _run():
            engine._client = AsyncMock()
            with patch.object(engine, "_get_query_embedding", AsyncMock(return_value=[0.1, 0.2])), \
                 patch.object(engine, "_get_sparse_embedding", return_value=([1], [0.5])), \
                 patch.object(engine, "_fetch_ast_matches", return_value=["### AST Symbol: `foo` (func)\nSignature: `def foo():`"]), \
                 patch.object(engine, "_fetch_hippo_subgraph", return_value=["[Hippo] Node"]), \
                 patch.object(engine, "_fetch_temporal_facts", return_value=[]), \
                 patch.object(engine, "_retrieve_qdrant_points", AsyncMock(return_value=["Unrelated doc"])), \
                 patch.object(engine, "_retrieve_qdrant_sparse_points", AsyncMock(return_value=[])):

                with patch.object(engine.reranker, "rerank", wraps=engine.reranker.rerank) as spy_rerank:
                    results = await engine.query("def foo", collection="test_col", top_k=3)
                    spy_rerank.assert_called_once()
                    assert len(results) > 0
                    assert "### AST Symbol: `foo`" in results[0]
            await engine.reranker.close()

        asyncio.run(_run())
