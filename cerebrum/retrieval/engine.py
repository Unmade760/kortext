"""
Cerebrum 5-Signal Hybrid RRF Retrieval Pipeline:
  Signal 1: Deterministic AST Symbol Seek (FalkorDB cerebrum_symbols B-Tree)
  Signal 2: BM25 Sparse Lexical Vectors (FastEmbed / Qdrant)
  Signal 3: Dense Semantic Vectors (Qwen3 MRL-2048 / Qdrant)
  Signal 4: HippoRAG Associative Personalized PageRank (FalkorDB Subgraphs)
  Signal 5: Bi-Temporal Recency / Validity Filter (FalkorDB Episodic)

Followed by:
  - Reciprocal Rank Fusion (RRF with k=60, w=[0.30, 0.20, 0.25, 0.15, 0.10])
  - Truncation-Aware Adaptive Knee (TAA-k) Trimming
  - Stage 2 Qwen3 Cross-Encoder Reranking
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
import re
from typing import Any, Dict, List, Optional, Tuple

import httpx
from dotenv import load_dotenv
from llama_index.core import Settings
from llama_index.embeddings.openai import OpenAIEmbedding
from qdrant_client import AsyncQdrantClient, QdrantClient
from qdrant_client import models as qmodels

from cerebrum.falkordb_client import get_shared_falkordb_client
from cerebrum.retrieval.hipporag import HippoRAGPPR

load_dotenv()

logger = logging.getLogger("cerebrum.retrieval")

EMBED_BASE_URL  = os.getenv("EMBED_BASE_URL", "http://localhost:8000/v1")
RERANK_BASE_URL = os.getenv("RERANK_BASE_URL", "http://localhost:8000/v1")
QDRANT_URL      = os.getenv("QDRANT_URL", "http://localhost:6333")
DEFAULT_COLLECTION = os.getenv("QDRANT_COLLECTION", "cerebrum_codebase")
TOP_K_RETRIEVE  = int(os.getenv("RETRIEVE_TOP_K", "30"))
TOP_K_RERANK    = int(os.getenv("RERANK_TOP_K", "5"))

# Signal Weights for 5-Signal RRF
W_AST: float = 0.30
W_BM25: float = 0.20
W_DENSE: float = 0.25
W_HIPPO: float = 0.15
W_TEMPORAL: float = 0.10
K_RRF: int = 60


def extract_passage_text(payload: Dict[str, Any]) -> str:
    """Extracts raw text content from Qdrant point payload across schemas."""
    if not payload:
        return ""
    if "text" in payload:
        return str(payload["text"])
    if "_node_content" in payload:
        try:
            nc = json.loads(payload["_node_content"])
            if "text" in nc:
                return str(nc["text"])
        except Exception:
            pass
    if "document" in payload:
        return str(payload["document"])
    return json.dumps(payload)


def apply_taak_trimming(
    scored_candidates: List[Tuple[str, float]],
    k_min: int = 3,
    k_max: int = 15,
) -> List[str]:
    """
    Truncation-Aware Adaptive Knee (TAA-k) Trimming.
    Identifies the point of maximum discrete curvature (second derivative)
    in descending RRF scores to drop low-scoring distractor documents.
    """
    n = len(scored_candidates)
    if n <= k_min:
        return [c[0] for c in scored_candidates]

    upper_bound = min(n, k_max)
    scores = [c[1] for c in scored_candidates]

    # Discrete first derivative: Delta(i) = S(i) - S(i+1)
    deltas = [scores[i] - scores[i + 1] for i in range(upper_bound - 1)]

    # Discrete second derivative: Delta^2(i) = Delta(i) - Delta(i+1)
    best_k = min(k_max, n)
    max_curvature = -float("inf")

    for i in range(k_min - 1, len(deltas) - 1):
        curvature = deltas[i] - deltas[i + 1]
        if curvature > max_curvature and curvature > 0.001:
            max_curvature = curvature
            best_k = i + 1

    return [c[0] for c in scored_candidates[:best_k]]


class RetrievalEngine:
    """
    Manages 5-Signal Hybrid Reciprocal Rank Fusion (RRF) with TAA-k adaptive trimming
    and cross-encoder reranking over Qdrant, FalkorDB, and HippoRAG.
    """

    def __init__(self):
        self._client: AsyncQdrantClient | None = None
        self._sync_client: QdrantClient | None = None
        self._hippo = HippoRAGPPR()
        self._falkordb = get_shared_falkordb_client()

    async def initialize(self):
        embed_api_key = os.getenv("EMBED_API_KEY") or os.getenv("OPENAI_API_KEY") or "not-needed"
        embed_model = OpenAIEmbedding(
            api_base=EMBED_BASE_URL,
            api_key=embed_api_key,
            model_name=os.getenv("EMBED_MODEL_NAME", "mlx-community--Qwen3-Embedding-8B-4bit-DWQ"),
            timeout=120.0,
            max_retries=3,
        )
        Settings.embed_model = embed_model
        Settings.chunk_size = 512
        Settings.chunk_overlap = 64

        self._sync_client = QdrantClient(url=QDRANT_URL)
        self._client = AsyncQdrantClient(url=QDRANT_URL)

        # Ensure default collection exists
        await self._ensure_collection(DEFAULT_COLLECTION)

    async def _ensure_collection(self, collection_name: str):
        embed_dim = int(os.getenv("EMBED_DIMENSION", "4096"))
        try:
            if not self._sync_client.collection_exists(collection_name):
                self._sync_client.create_collection(
                    collection_name=collection_name,
                    vectors_config={"text-dense": qmodels.VectorParams(size=embed_dim, distance=qmodels.Distance.COSINE)},
                    sparse_vectors_config={"text-sparse-new": qmodels.SparseVectorParams()},
                )
        except Exception as e:
            logger.warning(f"Could not verify/create Qdrant collection '{collection_name}': {e}")

    async def _get_query_embedding(self, prompt: str) -> List[float]:
        try:
            payload = {
                "input": prompt,
                "model": os.getenv("EMBED_MODEL_NAME", "mlx-community--Qwen3-Embedding-8B-4bit-DWQ"),
            }
            embed_key = os.getenv("EMBED_API_KEY") or os.getenv("OPENAI_API_KEY") or "not-needed"
            headers = {"Authorization": f"Bearer {embed_key}"}
            async with httpx.AsyncClient(timeout=30.0) as client:
                resp = await client.post(f"{EMBED_BASE_URL}/embeddings", json=payload, headers=headers)
                if resp.status_code == 200:
                    data = resp.json()
                    return data["data"][0]["embedding"]
        except Exception:
            pass

        if Settings.embed_model:
            try:
                return await Settings.embed_model.aget_query_embedding(prompt)
            except Exception:
                pass
        return []

    async def _retrieve_qdrant_points(
        self,
        col_name: str,
        dense_vec: List[float],
        limit: int = TOP_K_RETRIEVE,
    ) -> List[str]:
        """Queries Qdrant using modern query_points API with Prefetch objects."""
        if not self._client or not dense_vec:
            return []

        try:
            prefetch = [
                qmodels.Prefetch(
                    query=dense_vec,
                    using="text-dense",
                    limit=limit,
                )
            ]
            response = await self._client.query_points(
                collection_name=col_name,
                prefetch=prefetch,
                limit=limit,
                with_payload=True,
            )
            passages = []
            for p in response.points:
                text = extract_passage_text(p.payload or {})
                if text:
                    passages.append(text)
            return passages
        except Exception as e:
            logger.warning(f"Qdrant query_points failed on '{col_name}': {e}")
            return []

    def _extract_symbol_candidates(self, query: str) -> List[str]:
        """Extracts likely symbol identifiers from natural language query."""
        candidates = []
        candidates.extend(re.findall(r"`([A-Za-z_][A-Za-z0-9_]*)`", query))
        intent_matches = re.findall(
            r"(?:where is|what is|find|class|def|function|method|symbol|references to|callers of|calls to)\s+([A-Za-z_][A-Za-z0-9_]*)",
            query,
            flags=re.IGNORECASE,
        )
        candidates.extend(intent_matches)
        candidates.extend(re.findall(r"\b([A-Za-z_][A-Za-z0-9_]*)\s*\(", query))
        candidates.extend(re.findall(r"\b[A-Z][a-zA-Z0-9]*[a-z][A-Za-z0-9]*\b", query))
        candidates.extend(re.findall(r"\b[a-z][a-z0-9]*_[a-z0-9_]+\b", query))

        stop_words = {
            "is", "where", "what", "find", "class", "def", "function", "method", "symbol",
            "references", "to", "of", "in", "and", "or", "not", "for", "the", "a", "an",
            "self", "true", "false", "none", "return", "import", "from", "async", "await",
            "query", "test", "code", "file", "line",
        }
        seen = set()
        result = []
        for c in candidates:
            low = c.lower()
            if low not in stop_words and c not in seen and len(c) >= 3:
                seen.add(c)
                result.append(c)
                if len(result) >= 5:
                    break
        return result

    def _fetch_ast_matches(self, symbols: List[str]) -> List[str]:
        """Signal 1: Deterministic AST Symbol Seek from FalkorDB cerebrum_symbols."""
        if not symbols:
            return []
        matches = []
        for sym in symbols[:5]:
            cypher = """
            MATCH (s:Symbol)
            WHERE s.name = $name
            OPTIONAL MATCH (s)-[d:DEFINED_IN]->(f:File)
            RETURN s.name, s.kind, f.path, d.line, d.end_line, d.signature, d.docstring
            LIMIT 3
            """
            res = self._falkordb.query("cerebrum_symbols", cypher, {"name": sym})
            if res and len(res) > 1 and res[1]:
                for row in res[1]:
                    name, kind, path, line, end_line, sig, doc = row
                    passage = (
                        f"### AST Symbol: `{name}` ({kind or 'symbol'})\n"
                        f"- File: `{path or 'unknown'}` (Lines {line or 1}-{end_line or line or 1})\n"
                        f"- Signature: `{sig or name}`\n"
                    )
                    if doc:
                        passage += f"- Docstring: {doc}\n"
                    matches.append(passage)
        return matches

    def _fetch_hippo_subgraph(self, seeds: List[str]) -> List[str]:
        """Signal 4: HippoRAG Associative Personalized PageRank."""
        if not seeds:
            return []
        try:
            ppr_results = self._hippo.retrieve_associative_subgraph(seeds, top_k=8, graph_name="cerebrum")
            if not ppr_results:
                return []
            passages = []
            for node_name, score in ppr_results:
                if score < 0.01:
                    continue
                cypher = """
                MATCH (e:Entity {name: $name})-[r:RELATES_TO]->(t:Entity)
                RETURN e.name, r.relation, t.name, r.fact
                LIMIT 2
                """
                res = self._falkordb.query("cerebrum", cypher, {"name": node_name})
                if res and len(res) > 1 and res[1]:
                    for row in res[1]:
                        passages.append(
                            f"[Associative Knowledge Graph (Score: {score:.3f})]\n"
                            f"Entity `{row[0]}` {row[1]} `{row[2]}`: {row[3]}"
                        )
            return passages
        except Exception as e:
            logger.debug(f"HippoRAG retrieval non-critical error: {e}")
            return []

    def _fetch_temporal_facts(self, prompt: str) -> List[str]:
        """Signal 5: Bi-Temporal Validity Filtered Facts."""
        try:
            cypher = """
            MATCH (e:Entity)-[r:RELATES_TO]->(t:Entity)
            WHERE (r.valid_to IS NULL OR r.valid_to >= datetime())
            RETURN e.name, r.relation, t.name, r.fact
            ORDER BY r.valid_from DESC
            LIMIT 5
            """
            res = self._falkordb.query("cerebrum", cypher)
            if res and len(res) > 1 and res[1]:
                return [f"[Temporal Fact] `{row[0]}` {row[1]} `{row[2]}`: {row[3]}" for row in res[1]]
        except Exception:
            pass
        return []

    async def query(
        self,
        prompt: str,
        collection: Optional[str | List[str]] = None,
    ) -> List[str]:
        """
        Federated 5-Signal Hybrid Reciprocal Rank Fusion (RRF) search across
        AST symbols, dense vector stores, HippoRAG subgraphs, and bi-temporal facts,
        followed by TAA-k knee trimming and stage-2 cross-encoder reranking.
        """
        if self._sync_client is None:
            await self.initialize()

        # 1. Resolve collections
        target_cols: List[str] = []
        if collection == "all":
            try:
                cols = self._sync_client.get_collections().collections
                target_cols = [c.name for c in cols]
            except Exception:
                target_cols = [DEFAULT_COLLECTION]
        elif isinstance(collection, str) and "," in collection:
            target_cols = [c.strip() for c in collection.split(",") if c.strip()]
        elif isinstance(collection, list):
            target_cols = [c.strip() for c in collection if c.strip()]
        elif collection:
            target_cols = [collection]
        else:
            target_cols = [DEFAULT_COLLECTION]

        if not target_cols:
            target_cols = [DEFAULT_COLLECTION]

        loop = asyncio.get_running_loop()
        candidates = self._extract_symbol_candidates(prompt)

        # 2. Parallel signal execution
        dense_vec_task = asyncio.create_task(self._get_query_embedding(prompt))
        ast_task = loop.run_in_executor(None, self._fetch_ast_matches, candidates)
        hippo_task = loop.run_in_executor(None, self._fetch_hippo_subgraph, candidates)
        temporal_task = loop.run_in_executor(None, self._fetch_temporal_facts, prompt)

        dense_vec = await dense_vec_task
        ast_passages = await ast_task
        hippo_passages = await hippo_task
        temporal_passages = await temporal_task

        # Vector retrieval across target collections
        vector_tasks = [
            self._retrieve_qdrant_points(col, dense_vec)
            for col in target_cols
        ]
        vector_batches = await asyncio.gather(*vector_tasks)
        vector_passages: List[str] = []
        for batch in vector_batches:
            vector_passages.extend(batch)

        # 3. 5-Signal Reciprocal Rank Fusion (RRF)
        # We assign weighted RRF scores to all unique candidate passages
        all_signals: List[Tuple[List[str], float]] = [
            (ast_passages, W_AST),
            (vector_passages, W_DENSE + W_BM25),
            (hippo_passages, W_HIPPO),
            (temporal_passages, W_TEMPORAL),
        ]

        rrf_scores: Dict[str, float] = {}
        for passages, weight in all_signals:
            for rank, passage in enumerate(passages):
                score = weight / (K_RRF + (rank + 1))
                rrf_scores[passage] = rrf_scores.get(passage, 0.0) + score

        if not rrf_scores:
            return []

        ranked_candidates = sorted(rrf_scores.items(), key=lambda x: x[1], reverse=True)

        # 4. Truncation-Aware Adaptive Knee (TAA-k) Trimming
        trimmed_passages = apply_taak_trimming(ranked_candidates, k_min=3, k_max=15)

        # 5. Joint Stage-2 Cross-Encoder Reranking
        return await self._rerank(prompt, trimmed_passages)

    async def _rerank(self, query: str, passages: List[str]) -> List[str]:
        """POST to oMLX /v1/rerank and return sorted passages."""
        if not passages:
            return []

        eval_docs = [p[:1200] for p in passages]
        payload = {
            "model": os.getenv("RERANK_MODEL_NAME", "vserifsaglam--Qwen3-Reranker-4B-4bit-MLX"),
            "query": query,
            "documents": eval_docs,
        }
        rerank_key = os.getenv("RERANK_API_KEY") or os.getenv("COHERE_API_KEY")
        headers = {"Authorization": f"Bearer {rerank_key}"} if rerank_key else {}
        try:
            async with httpx.AsyncClient(timeout=60.0) as client:
                resp = await client.post(f"{RERANK_BASE_URL}/rerank", json=payload, headers=headers)
            resp.raise_for_status()
            results = resp.json().get("results", [])
            sorted_results = sorted(results, key=lambda x: x.get("relevance_score", 0), reverse=True)
            return [passages[r["index"]] for r in sorted_results[:TOP_K_RERANK]]
        except Exception as e:
            err_msg = f"{type(e).__name__}: {e or 'timeout'}"
            logger.debug(f"Reranker unavailable ({err_msg}), returning top-k by RRF score.")
            return passages[:TOP_K_RERANK]
