"""
Kortext 5-Signal Hybrid RRF Retrieval Pipeline:
  Signal 1: Deterministic AST Symbol Seek (FalkorDB kortext_symbols B-Tree)
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
from typing import Any, Dict, List, Optional, Tuple, TypedDict
from pathlib import Path

from kortext.chunking.token_utils import count_tokens

import httpx
from dotenv import load_dotenv
from fastembed import SparseTextEmbedding
from llama_index.core import Settings
from llama_index.embeddings.openai import OpenAIEmbedding
from qdrant_client import AsyncQdrantClient, QdrantClient
from qdrant_client import models as qmodels

from kortext.embeddings import get_dense_embedder
from kortext.falkordb_client import get_shared_falkordb_client
from kortext.retrieval.hipporag import HippoRAGPPR
from kortext.retrieval.reranker import RerankerEngine
from kortext.retrieval.retention import (
    DEFAULT_FLOOR,
    compute_age_hours,
    compute_age_seconds,
    compute_weibull_retention,
)
from kortext.symbols.seek import extract_symbol_candidates

load_dotenv()

logger = logging.getLogger("kortext.retrieval")

_SPARSE_MODEL: Optional[SparseTextEmbedding] = None


def get_sparse_model() -> Optional[SparseTextEmbedding]:
    """Lazily initializes and returns the singleton FastEmbed BM25 sparse model."""
    global _SPARSE_MODEL
    if _SPARSE_MODEL is None:
        try:
            _SPARSE_MODEL = SparseTextEmbedding(model_name="Qdrant/bm25")
        except Exception as exc:
            logger.warning(f"Failed to initialize sparse model: {exc}")
            return None
    return _SPARSE_MODEL

EMBED_BASE_URL  = os.getenv("EMBED_BASE_URL", "http://127.0.0.1:8000/v1").replace("://localhost", "://127.0.0.1")
RERANK_BASE_URL = os.getenv("RERANK_BASE_URL", "http://127.0.0.1:8000/v1").replace("://localhost", "://127.0.0.1")
QDRANT_URL      = os.getenv("QDRANT_URL", "").strip()


from kortext._home import KORTEXT_HOME

CEREBRUM_HOME = KORTEXT_HOME

DEFAULT_QDRANT_PATH = KORTEXT_HOME / "qdrant"
if not (os.getenv("KORTEXT_HOME") or os.getenv("CEREBRUM_HOME")) and not DEFAULT_QDRANT_PATH.exists() and (Path.home() / ".cerebrum" / "qdrant").exists():
    DEFAULT_QDRANT_PATH = Path.home() / ".cerebrum" / "qdrant"

DEFAULT_COLLECTION = os.getenv("KORTEXT_COLLECTION", os.getenv("QDRANT_COLLECTION", "kortext_codebase"))
DEFAULT_DATABASE = os.getenv("KORTEXT_DATABASE", os.getenv("FALKORDB_DATABASE", "kortext"))
DEFAULT_SYMBOLS_GRAPH = os.getenv("KORTEXT_SYMBOLS_GRAPH", os.getenv("FALKORDB_SYMBOLS_GRAPH", "kortext_symbols"))

TOP_K_RETRIEVE  = int(os.getenv("RETRIEVE_TOP_K", "30"))
TOP_K_RERANK    = int(os.getenv("RERANK_TOP_K", "5"))

# Signal Weights for 5-Signal RRF
W_AST: float = 0.30
W_BM25: float = 0.20
W_DENSE: float = 0.25
W_HIPPO: float = 0.15
W_TEMPORAL: float = 0.10
K_RRF: int = 60

DEFAULT_FUSION_WEIGHTS: Dict[str, float] = {
    "ast": W_AST,          # 0.30
    "bm25": W_BM25,        # 0.20
    "dense": W_DENSE,      # 0.25
    "hippo": W_HIPPO,      # 0.15
    "temporal": W_TEMPORAL,# 0.10
}

# Adaptive RRF Weights:
# Symbolic / Code queries elevate AST (>= 0.35) and BM25 lexical precision
SYMBOLIC_FUSION_WEIGHTS: Dict[str, float] = {
    "ast": 0.40,
    "bm25": 0.25,
    "dense": 0.15,
    "hippo": 0.10,
    "temporal": 0.10,
}

# Prose / Conceptual queries elevate associative HippoRAG and semantic dense vectors
PROSE_FUSION_WEIGHTS: Dict[str, float] = {
    "ast": 0.10,
    "bm25": 0.15,
    "dense": 0.35,
    "hippo": 0.25,
    "temporal": 0.15,
}

# Programming keywords & constructs commonly indicating code intent
_PROGRAMMING_KEYWORDS_PATTERN = re.compile(
    r"\b("
    r"def|class|function|fn|func|method|"
    r"async|await|return|returns|yield|"
    r"import|from|export|"
    r"var|let|const|"
    r"lambda|"
    r"raise|throw|except|catch|finally|try|"
    r"interface|struct|enum|type|impl|trait|"
    r"public|private|protected|static|"
    r"self|cls"
    r")\b",
    re.IGNORECASE,
)

# CamelCase / PascalCase pattern (e.g. RetrievalEngine, getUserData, HippoRAGPPR)
_CAMEL_CASE_PATTERN = re.compile(r"\b[a-z]+[A-Z0-9][a-zA-Z0-9]*\b|\b[A-Z]+[a-z]+[A-Z][a-zA-Z0-9]*\b")

# Dotted symbol / module / code path (e.g. engine.py, os.path, kortext.retrieval, foo.bar)
# Excludes sentence-ending dots by requiring letters/identifier chars around the dot.
_DOTTED_SYMBOL_PATTERN = re.compile(r"(?<=[a-zA-Z_])\.(?=[a-zA-Z0-9_])")

# Parentheses indicating function calls (e.g. foo(), bar(x), compute())
_CALL_PARENS_PATTERN = re.compile(r"\b[a-zA-Z_]\w*\s*\([^)]*\)")

# Backticks wrapping code or operators
_CODE_SYNTAX_PATTERN = re.compile(r"`[^`]+`|::|->|=>|==|!=|\+=|-=|\*=")


def is_ci_mode() -> bool:
    """Checks whether KORTEXT_CI_MODE (or legacy CEREBRUM_CI_MODE) is enabled in the environment."""
    return os.getenv("KORTEXT_CI_MODE", os.getenv("CEREBRUM_CI_MODE", "")).strip().lower() in ("1", "true", "yes")


def is_symbolic_query(query: str) -> bool:
    """
    Detects if a query is symbolic / code-oriented versus natural language prose / conceptual.
    
    Returns True if the query contains:
      - snake_case identifiers (containing '_')
      - camelCase or PascalCase identifiers
      - Dotted symbol / module paths (e.g. engine.py, os.getenv)
      - Parentheses indicating function calls (e.g. foo(), compute(x, y))
      - Programming keywords (e.g. def, class, return, import)
      - Backticks or code operators (e.g. `symbol`, ->, ::)
    """
    if not query or not query.strip():
        return False

    q = query.strip()
    if "_" in q:
        return True
    if _CODE_SYNTAX_PATTERN.search(q):
        return True
    if _PROGRAMMING_KEYWORDS_PATTERN.search(q):
        return True
    if _CAMEL_CASE_PATTERN.search(q):
        return True
    if _DOTTED_SYMBOL_PATTERN.search(q):
        return True
    if _CALL_PARENS_PATTERN.search(q):
        return True
    return False


def redistribute_weights(
    weights: Dict[str, float],
    inactive_keys: Optional[List[str]] = None,
) -> Dict[str, float]:
    """
    Redistributes the weight mass of inactive modalities proportionally
    across all active modalities so that the active weights sum to 1.0.
    """
    if inactive_keys is None:
        inactive_keys = ["dense"]

    inactive_set = set(inactive_keys)
    active_sum = sum(w for k, w in weights.items() if k not in inactive_set)
    if active_sum <= 0:
        return dict(weights)

    total_weight = sum(weights.values())
    new_weights: Dict[str, float] = {}
    for k, w in weights.items():
        if k in inactive_set:
            new_weights[k] = 0.0
        else:
            new_weights[k] = (w / active_sum) * total_weight
    return new_weights


def redistribute_ci_weights(weights: Optional[Dict[str, float]] = None) -> Dict[str, float]:
    """Redistributes dense weight across active modalities for CI mode."""
    target_weights = dict(weights) if weights is not None else dict(DEFAULT_FUSION_WEIGHTS)
    return redistribute_weights(target_weights, inactive_keys=["dense"])


def compute_adaptive_weights(
    query: str,
    ci_mode: Optional[bool] = None,
    dense_available: bool = True,
    suppress_ast_signal: bool = False,
) -> Dict[str, float]:
    """
    Computes adaptive 5-signal RRF weights based on query type (symbolic vs prose)
    and environmental availability (CI mode or dense embedder offline).

    - If query is symbolic/code-oriented: elevates AST (>= 0.35) and BM25.
    - If query is prose/conceptual: maintains or elevates HippoRAG and semantic weights.
    - If CI mode is enabled (CEREBRUM_CI_MODE="1") or dense_available=False:
      redistributes dense weight mass proportionally across remaining active modalities.
    - If suppress_ast_signal=True:
      zeros out AST weight and redistributes its mass across remaining active modalities.
    """
    if ci_mode is None:
        ci_mode = is_ci_mode()

    if is_symbolic_query(query):
        weights = dict(SYMBOLIC_FUSION_WEIGHTS)
    else:
        weights = dict(PROSE_FUSION_WEIGHTS)

    inactive_keys: List[str] = []
    if ci_mode or not dense_available:
        inactive_keys.append("dense")
    if suppress_ast_signal:
        inactive_keys.append("ast")

    if inactive_keys:
        weights = redistribute_weights(weights, inactive_keys=inactive_keys)

    return weights



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


class FederatedRetrievalResult(TypedDict, total=False):
    """Structured envelope for 4-tier federated retrieval."""
    query: str
    symbolic_context: List[Any]
    code_chunks: List[str]
    episodic_history: List[str]
    architectural_overview: Optional[str]
    total_estimated_tokens: int
    markdown: Optional[str]


def apply_knapsack_mmr(
    candidates: List[Any],
    query: str,
    token_budget: int = 400,
    lambda_param: float = 0.7,
    diversity_threshold: float = 0.65,
) -> List[str]:
    """
    Selects a diverse subset of episodic candidates within the token budget
    using Maximal Marginal Relevance (MMR) and knapsack capacity constraints.
    Filters out near-duplicates exceeding the diversity threshold.
    """
    if not candidates or token_budget <= 0:
        return []

    norm_candidates: List[str] = [
        c if isinstance(c, str) else json.dumps(c) for c in candidates if c
    ]
    if not norm_candidates:
        return []

    query_tokens = set(re.findall(r"\w+", query.lower()))

    def token_sim(a_words: set[str], b_words: set[str]) -> float:
        if not a_words or not b_words:
            return 0.0
        intersection = len(a_words & b_words)
        union = len(a_words | b_words)
        return intersection / union if union > 0 else 0.0

    cand_word_sets = [set(re.findall(r"\w+", c.lower())) for c in norm_candidates]

    selected: List[str] = []
    selected_word_sets: List[set[str]] = []
    current_tokens = 0
    remaining_indices = list(range(len(norm_candidates)))

    while remaining_indices:
        best_idx = None
        best_score = -float("inf")

        for idx in remaining_indices:
            cand_text = norm_candidates[idx]
            cand_tokens = count_tokens(cand_text)

            # Knapsack constraint
            if current_tokens + cand_tokens > token_budget:
                continue

            cand_words = cand_word_sets[idx]

            # Redundancy penalty (MMR) against already selected items
            if not selected_word_sets:
                redundancy = 0.0
            else:
                redundancy = max(token_sim(cand_words, sel_words) for sel_words in selected_word_sets)

            # Prune near-duplicates
            if redundancy >= diversity_threshold:
                continue

            # Relevance to query: Jaccard similarity + initial rank bias
            query_rel = token_sim(cand_words, query_tokens)
            rank_prior = 1.0 / (1.0 + 0.1 * idx)
            relevance = 0.6 * query_rel + 0.4 * rank_prior

            score = lambda_param * relevance - (1.0 - lambda_param) * redundancy

            if score > best_score:
                best_score = score
                best_idx = idx

        if best_idx is None or best_score <= 0.0:
            break

        cand_text = norm_candidates[best_idx]
        selected.append(cand_text)
        selected_word_sets.append(cand_word_sets[best_idx])
        current_tokens += count_tokens(cand_text)
        remaining_indices.remove(best_idx)

    return selected


def _is_file_in_workspace(file_path: Optional[str], ws_root: str) -> bool:
    if not file_path:
        return False
    fp_str = str(file_path)
    ws_str = str(ws_root)
    if fp_str.startswith(ws_str):
        return True
    try:
        p_file = Path(fp_str)
        p_ws = Path(ws_str).resolve()
        if p_file.is_absolute():
            resolved = p_file.resolve()
            return resolved == p_ws or p_ws in resolved.parents
        else:
            if (p_ws / p_file).exists():
                return True
            resolved = p_file.resolve()
            return resolved == p_ws or p_ws in resolved.parents
    except Exception:
        pass
    return False


class RetrievalEngine:
    """
    Manages 5-Signal Hybrid Reciprocal Rank Fusion (RRF) with TAA-k adaptive trimming
    and cross-encoder reranking over Qdrant, FalkorDB, and HippoRAG.
    """

    def __init__(self):
        self._client: AsyncQdrantClient | None = None
        self._hippo = HippoRAGPPR()
        self._falkordb = get_shared_falkordb_client()
        self._candidate_metadata: Dict[str, Dict[str, Any]] = {}
        self.reranker = RerankerEngine()
        self._symbol_seek = None
        self._episodic = None

    @property
    def symbol_seek(self):
        if self._symbol_seek is None:
            from kortext.symbols.seek import SymbolSeekEngine
            self._symbol_seek = SymbolSeekEngine()
        return self._symbol_seek

    @symbol_seek.setter
    def symbol_seek(self, val):
        self._symbol_seek = val

    @property
    def episodic(self):
        if self._episodic is None:
            from kortext.episodic import AgentNativeEpisodicDriver
            self._episodic = AgentNativeEpisodicDriver()
        return self._episodic

    @episodic.setter
    def episodic(self, val):
        self._episodic = val

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

        if QDRANT_URL:
            self._client = AsyncQdrantClient(url=QDRANT_URL)
        else:
            DEFAULT_QDRANT_PATH.mkdir(parents=True, exist_ok=True)
            self._client = AsyncQdrantClient(path=str(DEFAULT_QDRANT_PATH))

        # Ensure default collection exists
        await self._ensure_collection(DEFAULT_COLLECTION)

    async def _ensure_collection(self, collection_name: str):
        if os.getenv("EMBED_DIMENSION"):
            embed_dim = int(os.getenv("EMBED_DIMENSION"))
        else:
            embed_dim = get_dense_embedder().dimension
        try:
            if not await self._client.collection_exists(collection_name):
                await self._client.create_collection(
                    collection_name=collection_name,
                    vectors_config={"text-dense": qmodels.VectorParams(size=embed_dim, distance=qmodels.Distance.COSINE)},
                    sparse_vectors_config={"text-sparse-new": qmodels.SparseVectorParams()},
                )
        except Exception as e:
            logger.warning(f"Could not verify/create Qdrant collection '{collection_name}': {e}")

    async def _get_query_embedding(self, prompt: str) -> List[float]:
        if not prompt or not prompt.strip():
            return []
        try:
            embedder = get_dense_embedder()
            if hasattr(embedder, "aembed_query") and callable(embedder.aembed_query):
                return await embedder.aembed_query(prompt)
            return embedder.embed_query(prompt)
        except Exception as e:
            logger.warning(f"Failed to generate query embedding: {e}")
            return []

    def _get_sparse_embedding(self, prompt: str) -> Optional[Tuple[List[int], List[float]]]:
        """Generates sparse indices and values using fastembed Qdrant/bm25."""
        if not prompt or not prompt.strip():
            return None
        try:
            model = get_sparse_model()
            if model is None:
                return None
            embeddings = list(model.query_embed(prompt))
            if not embeddings:
                return None
            emb = embeddings[0]
            indices = [int(i) for i in emb.indices]
            values = [float(v) for v in emb.values]
            if not indices or not values:
                return None
            return indices, values
        except Exception as e:
            logger.warning(f"Failed to generate sparse embedding: {e}")
            return None

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
            response = await self._client.query_points(
                collection_name=col_name,
                query=dense_vec,
                using="text-dense",
                limit=limit,
                with_payload=True,
            )
            passages = []
            for p in response.points:
                payload = getattr(p, "payload", None) or {}
                text = extract_passage_text(payload)
                if text:
                    passages.append(text)
                    if isinstance(payload, dict):
                        ts = payload.get("timestamp") or payload.get("created_at") or payload.get("valid_from")
                        created_at = payload.get("created_at")
                        valid_from = payload.get("valid_from")
                        imp = payload.get("importance")
                        if ts is not None or imp is not None:
                            self._candidate_metadata[text] = {
                                "timestamp": ts,
                                "created_at": created_at,
                                "valid_from": valid_from,
                                "importance": imp if imp is not None else 5,
                                "tier": "dense",
                            }
            return passages
        except Exception as e:
            logger.warning(f"Qdrant query_points failed on '{col_name}': {e}")
            return []

    async def _retrieve_qdrant_sparse_points(
        self,
        col_name: str,
        sparse_indices: List[int],
        sparse_values: List[float],
        limit: int = TOP_K_RETRIEVE,
    ) -> List[str]:
        """Queries Qdrant points with using='text-sparse-new' and SparseVector."""
        if not self._client or not sparse_indices or not sparse_values:
            return []

        try:
            response = await self._client.query_points(
                collection_name=col_name,
                query=qmodels.SparseVector(indices=sparse_indices, values=sparse_values),
                using="text-sparse-new",
                limit=limit,
                with_payload=True,
            )
            passages = []
            for p in response.points:
                payload = getattr(p, "payload", None) or {}
                text = extract_passage_text(payload)
                if text:
                    passages.append(text)
                    if isinstance(payload, dict):
                        ts = payload.get("timestamp") or payload.get("created_at") or payload.get("valid_from")
                        created_at = payload.get("created_at")
                        valid_from = payload.get("valid_from")
                        imp = payload.get("importance")
                        if ts is not None or imp is not None:
                            self._candidate_metadata[text] = {
                                "timestamp": ts,
                                "created_at": created_at,
                                "valid_from": valid_from,
                                "importance": imp if imp is not None else 5,
                                "tier": "sparse",
                            }
            return passages
        except Exception as e:
            logger.warning(f"Qdrant sparse query_points failed on '{col_name}': {e}")
            return []

    extract_symbol_candidates = staticmethod(extract_symbol_candidates)

    def _extract_symbol_candidates(self, query: str) -> List[str]:
        """Extracts likely symbol identifiers from natural language query (canonical seek)."""
        return extract_symbol_candidates(query)

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
            res = self._falkordb.query(DEFAULT_SYMBOLS_GRAPH, cypher, {"name": sym})
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
            ppr_results = self._hippo.retrieve_associative_subgraph(seeds, top_k=8, graph_name=DEFAULT_DATABASE)
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
                res = self._falkordb.query(DEFAULT_DATABASE, cypher, {"name": node_name})
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
            from datetime import datetime, timezone
            now_iso = datetime.now(timezone.utc).isoformat()
            cypher = """
            MATCH (e:Entity)-[r:RELATES_TO]->(t:Entity)
            WHERE (r.valid_to IS NULL OR r.valid_to >= $now)
            RETURN e.name, r.relation, t.name, r.fact, r.valid_from, r.importance
            ORDER BY r.valid_from DESC
            LIMIT 5
            """
            res = self._falkordb.query(DEFAULT_DATABASE, cypher, {"now": now_iso})
            if res and len(res) > 1 and res[1]:
                passages = []
                for row in res[1]:
                    passage = f"[Temporal Fact] `{row[0]}` {row[1]} `{row[2]}`: {row[3]}"
                    passages.append(passage)
                    valid_from = row[4] if len(row) > 4 else None
                    importance = row[5] if len(row) > 5 else 5
                    self._candidate_metadata[passage] = {
                        "valid_from": valid_from,
                        "importance": importance if importance is not None else 5,
                        "tier": "temporal",
                    }
                return passages
        except Exception:
            pass
        return []

    def get_adaptive_weights(
        self,
        query: str,
        dense_available: bool = True,
        ci_mode: Optional[bool] = None,
        suppress_ast_signal: bool = False,
    ) -> Dict[str, float]:
        """Calculates adaptive RRF weights for a given query and environment."""
        return compute_adaptive_weights(
            query=query,
            ci_mode=ci_mode,
            dense_available=dense_available,
            suppress_ast_signal=suppress_ast_signal,
        )

    def _rank_candidates(
        self,
        signals: List[Tuple[List[Any], float]] | Dict[str, List[Any]],
        candidate_metadata: Optional[Dict[str, Dict[str, Any]]] = None,
        retention_weight: float = 1.0,
        weights: Optional[Dict[str, float]] = None,
    ) -> List[Tuple[str, float]]:
        """
        Merges and scores candidates across retrieval tiers using
        Reciprocal Rank Fusion (RRF) modulated by Stretched Weibull Decay retention.

        Score per candidate:
            score(c) = sum_{tier} ( w_tier / (K_RRF + rank) ) * effective_retention(c)

        Where effective_retention(c) = (1.0 - rw) + (rw * retention(c)),
        and retention(c) is computed from delta_t / age_hours and importance via compute_weibull_retention,
        gracefully decaying older memories down to the biological floor.
        """
        rrf_scores: Dict[str, float] = {}
        meta_lookup = dict(self._candidate_metadata)
        if candidate_metadata:
            meta_lookup.update(candidate_metadata)

        if isinstance(signals, dict):
            active_weights = dict(weights) if weights is not None else dict(DEFAULT_FUSION_WEIGHTS)
            if is_ci_mode() or not signals.get("dense"):
                active_weights = redistribute_weights(active_weights, inactive_keys=["dense"])
            signal_list: List[Tuple[List[Any], float]] = [
                (items, active_weights.get(tier, 0.0))
                for tier, items in signals.items()
            ]
        else:
            signal_list = signals

        for items, weight in signal_list:
            for rank, item in enumerate(items):
                passage: str
                item_age: Optional[float] = None
                item_imp: Optional[int] = None
                item_meta_dict: Dict[str, Any] = {}

                if isinstance(item, str):
                    passage = item
                elif isinstance(item, tuple):
                    passage = str(item[0])
                    if len(item) > 1:
                        if isinstance(item[1], dict):
                            item_meta_dict.update(item[1])
                        elif isinstance(item[1], (int, float)):
                            item_age = float(item[1])
                    if len(item) > 2:
                        try:
                            item_imp = int(item[2])
                        except (ValueError, TypeError):
                            pass
                elif isinstance(item, dict):
                    passage = str(item.get("text") or item.get("passage") or item.get("document") or item)
                    item_meta_dict.update(item)
                    if isinstance(item.get("metadata"), dict):
                        item_meta_dict.update(item["metadata"])
                else:
                    passage = getattr(item, "text", None) or getattr(item, "passage", str(item))
                    for attr in ("age_hours", "delta_hours", "delta_t", "importance", "timestamp", "created_at", "valid_from"):
                        val = getattr(item, attr, None)
                        if val is not None:
                            item_meta_dict[attr] = val
                    item_metadata_attr = getattr(item, "metadata", None)
                    if isinstance(item_metadata_attr, dict):
                        item_meta_dict.update(item_metadata_attr)

                # Merge looked-up metadata with inline item metadata
                meta: Dict[str, Any] = dict(meta_lookup.get(passage, {}))
                meta.update(item_meta_dict)

                # Extract elapsed delta_t / age_hours
                age_hours = item_age if item_age is not None else (
                    meta.get("age_hours") or meta.get("delta_hours")
                )
                if age_hours is None and "delta_t" in meta and "lam" not in meta:
                    raw_dt = meta["delta_t"]
                    if isinstance(raw_dt, (int, float)):
                        age_hours = raw_dt if raw_dt < 1e5 else raw_dt / 3600.0

                if age_hours is None:
                    ts = (
                        meta.get("timestamp")
                        or meta.get("created_at")
                        or meta.get("valid_from")
                    )
                    if ts is not None:
                        age_hours = compute_age_hours(ts)

                importance = item_imp if item_imp is not None else meta.get("importance", 5)

                if "delta_t" in meta and "lam" in meta:
                    retention = compute_weibull_retention(
                        delta_t=meta["delta_t"],
                        lam=meta["lam"],
                        k=meta.get("k", 0.65),
                        strength=meta.get("strength", 1.0),
                        floor=meta.get("floor", DEFAULT_FLOOR),
                    )
                elif age_hours is not None:
                    retention = compute_weibull_retention(
                        delta_hours=age_hours,
                        importance=importance,
                        strength=meta.get("strength", 1.0),
                    )
                else:
                    retention = 1.0

                rw = meta.get("retention_weight", retention_weight)
                effective_retention = (1.0 - rw) + (rw * retention)
                score = (weight / (K_RRF + (rank + 1))) * effective_retention
                rrf_scores[passage] = rrf_scores.get(passage, 0.0) + score

        if not rrf_scores:
            return []

        return sorted(rrf_scores.items(), key=lambda x: x[1], reverse=True)

    async def retrieve(
        self,
        prompt: str,
        collection: Optional[str | List[str]] = None,
        **kwargs: Any,
    ) -> List[str]:
        """
        Federated 5-Signal Hybrid Reciprocal Rank Fusion (RRF) search across
        AST symbols, dense vector stores, HippoRAG subgraphs, and bi-temporal facts,
        factoring in Weibull retention decay, followed by TAA-k trimming and stage-2 reranking.
        """
        return await self.query(prompt=prompt, collection=collection, **kwargs)

    async def query(
        self,
        prompt: str,
        collection: Optional[str | List[str]] = None,
        retention_weight: float = 1.0,
        weights: Optional[Dict[str, float]] = None,
        top_k: int = TOP_K_RERANK,
        limit: Optional[int] = None,
        suppress_ast_signal: bool = False,
        **kwargs: Any,
    ) -> List[str]:
        """
        Federated 5-Signal Hybrid Reciprocal Rank Fusion (RRF) search across
        AST symbols, dense vector stores, HippoRAG subgraphs, and bi-temporal facts,
        followed by TAA-k knee trimming and stage-2 cross-encoder reranking.
        """
        if limit is not None:
            top_k = limit
        self._candidate_metadata.clear()
        if self._client is None:
            await self.initialize()

        # 1. Resolve collections
        target_cols: List[str] = []
        if collection == "all":
            try:
                cols = await self._client.get_collections()
                target_cols = [c.name for c in cols.collections]
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

        # Resolve target collections with backward compatibility
        if self._client is not None and target_cols:
            try:
                available_cols_resp = await self._client.get_collections()
                available_names = [c.name for c in available_cols_resp.collections]
                resolved_cols: List[str] = []
                for col in target_cols:
                    if col in available_names:
                        resolved_cols.append(col)
                    elif col in ("kortext_codebase", "kortext") and "cerebrum_codebase" in available_names:
                        resolved_cols.append("cerebrum_codebase")
                    elif col in ("cerebrum_codebase", "cerebrum") and "kortext_codebase" in available_names:
                        resolved_cols.append("kortext_codebase")
                    else:
                        resolved_cols.append(col)
                if resolved_cols:
                    target_cols = resolved_cols
            except Exception:
                pass

        loop = asyncio.get_running_loop()
        candidates = self._extract_symbol_candidates(prompt)

        # 2. Parallel signal execution
        dense_vec_task = asyncio.create_task(self._get_query_embedding(prompt))
        sparse_vec_task = loop.run_in_executor(None, self._get_sparse_embedding, prompt)
        if suppress_ast_signal:
            ast_task = None
        else:
            ast_task = loop.run_in_executor(None, self._fetch_ast_matches, candidates)
        hippo_task = loop.run_in_executor(None, self._fetch_hippo_subgraph, candidates)
        temporal_task = loop.run_in_executor(None, self._fetch_temporal_facts, prompt)

        gather_tasks = [dense_vec_task, sparse_vec_task]
        if ast_task is not None:
            gather_tasks.append(ast_task)
        gather_tasks.extend([hippo_task, temporal_task])

        gathered_res = await asyncio.gather(*gather_tasks)
        dense_vec = gathered_res[0]
        sparse_res = gathered_res[1]
        if ast_task is not None:
            ast_passages = gathered_res[2]
            hippo_passages = gathered_res[3]
            temporal_passages = gathered_res[4]
        else:
            ast_passages = []
            hippo_passages = gathered_res[2]
            temporal_passages = gathered_res[3]

        def _is_ast_passage(text: Any) -> bool:
            s = str(text).strip()
            return s.startswith("### AST Symbol:") or "### ast symbol:" in s.lower()

        if suppress_ast_signal:
            hippo_passages = [p for p in hippo_passages if not _is_ast_passage(p)]
            temporal_passages = [p for p in temporal_passages if not _is_ast_passage(p)]

        sparse_indices, sparse_values = sparse_res if sparse_res else ([], [])

        # Compute adaptive weights prior to multi-collection fusion
        if weights is not None:
            active_weights = dict(weights)
            if suppress_ast_signal:
                active_weights = redistribute_weights(active_weights, inactive_keys=["ast"])
        else:
            dense_available = bool(dense_vec) and not is_ci_mode()
            active_weights = compute_adaptive_weights(
                prompt,
                ci_mode=is_ci_mode(),
                dense_available=dense_available,
                suppress_ast_signal=suppress_ast_signal,
            )

        w_dense = active_weights.get("dense", W_DENSE)
        w_bm25 = active_weights.get("bm25", W_BM25)

        # Vector retrieval across target collections (dense + sparse in parallel)
        dense_tasks = [
            self._retrieve_qdrant_points(col, dense_vec)
            for col in target_cols
        ]
        sparse_tasks = [
            self._retrieve_qdrant_sparse_points(col, sparse_indices, sparse_values)
            for col in target_cols
        ]
        dense_batches, sparse_batches = await asyncio.gather(
            asyncio.gather(*dense_tasks),
            asyncio.gather(*sparse_tasks),
        )

        if suppress_ast_signal:
            dense_batches = [
                [p for p in batch if not _is_ast_passage(p)]
                for batch in dense_batches
            ]
            sparse_batches = [
                [p for p in batch if not _is_ast_passage(p)]
                for batch in sparse_batches
            ]

        # Multi-Collection RRF Normalization:
        # Score candidates per collection locally:
        # local_score(p) = (w_dense / (60 + rank_dense + 1)) + (w_bm25 / (60 + rank_sparse + 1))
        # Normalize within each collection, then merge across collections by normalized score.
        merged_scores: Dict[str, float] = {}
        for i in range(len(target_cols)):
            d_batch = dense_batches[i] if i < len(dense_batches) else []
            s_batch = sparse_batches[i] if i < len(sparse_batches) else []

            d_ranks = {p: r for r, p in enumerate(d_batch)}
            s_ranks = {p: r for r, p in enumerate(s_batch)}

            col_candidates = list(dict.fromkeys(d_batch + s_batch))
            if not col_candidates:
                continue

            local_scores: Dict[str, float] = {}
            for p in col_candidates:
                score_val = 0.0
                if p in d_ranks:
                    score_val += w_dense / (K_RRF + d_ranks[p] + 1)
                if p in s_ranks:
                    score_val += w_bm25 / (K_RRF + s_ranks[p] + 1)
                local_scores[p] = score_val

            max_local = max(local_scores.values()) if local_scores else 0.0
            for p, sc in local_scores.items():
                norm_sc = (sc / max_local) if max_local > 0.0 else 0.0
                merged_scores[p] = max(merged_scores.get(p, 0.0), norm_sc)

        sorted_vector_candidates = sorted(
            merged_scores.keys(),
            key=lambda p: merged_scores[p],
            reverse=True,
        )

        all_dense = {p for batch in dense_batches for p in batch}
        all_sparse = {p for batch in sparse_batches for p in batch}
        dense_passages: List[str] = [p for p in sorted_vector_candidates if p in all_dense]
        sparse_passages: List[str] = [p for p in sorted_vector_candidates if p in all_sparse]

        # 3. 5-Signal Reciprocal Rank Fusion (RRF) with Weibull Retention Decay
        all_signals: List[Tuple[List[Any], float]] = [
            (ast_passages, active_weights.get("ast", W_AST)),
            (sparse_passages, active_weights.get("bm25", W_BM25)),
            (dense_passages, active_weights.get("dense", W_DENSE)),
            (hippo_passages, active_weights.get("hippo", W_HIPPO)),
            (temporal_passages, active_weights.get("temporal", W_TEMPORAL)),
        ]

        ranked_candidates = self._rank_candidates(all_signals, retention_weight=retention_weight)
        if not ranked_candidates:
            return []

        # 4. Truncation-Aware Adaptive Knee (TAA-k) Trimming
        trimmed_passages = apply_taak_trimming(ranked_candidates, k_min=3, k_max=15)
        if suppress_ast_signal:
            trimmed_passages = [p for p in trimmed_passages if not _is_ast_passage(p)]

        # 5. Joint Stage-2 Cross-Encoder Reranking
        score_lookup = dict(ranked_candidates)
        candidates = [
            {
                "text": p,
                "score": score_lookup.get(p, 0.0),
                "metadata": self._candidate_metadata.get(p, {}),
            }
            for p in trimmed_passages
        ]
        reranked = await self.reranker.rerank(prompt, candidates, top_k=top_k)
        passages = [c["text"] for c in reranked if isinstance(c, dict) and "text" in c]
        if suppress_ast_signal:
            passages = [p for p in passages if not _is_ast_passage(p)]
        return passages

    async def _fetch_tier3_overview(
        self,
        workspace_root: Optional[str],
        query: str,
        budget: int,
        detail_level: str = "balanced",
        collection: Optional[str] = None,
    ) -> Optional[str]:
        """
        Retrieves architectural file skeleton chunks or top-level symbols/summaries.
        - If detail_level == 'compact': omits Tier 3 (returns None).
        - If detail_level == 'balanced': brief outline if workspace_root is requested and budget permits.
        - If detail_level in ('comprehensive', 'full'): comprehensive system outline up to tier3 budget.
        """
        if budget <= 0 or detail_level == "compact":
            return None

        if detail_level == "balanced" and not workspace_root:
            return None

        limit = 2 if detail_level == "balanced" else 8
        target_col = collection or DEFAULT_COLLECTION
        skeleton_texts: List[str] = []

        # 1. Query Qdrant for ast_skeleton chunks (chunk_type: "ast_skeleton")
        if self._client is not None:
            try:
                filter_cond = qmodels.Filter(
                    must=[
                        qmodels.FieldCondition(
                            key="chunk_type",
                            match=qmodels.MatchValue(value="ast_skeleton"),
                        )
                    ]
                )
                points = []
                dense_vec = await self._get_query_embedding(query)
                if dense_vec and not is_ci_mode():
                    try:
                        res = await self._client.query_points(
                            collection_name=target_col,
                            query=dense_vec,
                            query_filter=filter_cond,
                            using="text-dense",
                            limit=limit,
                            with_payload=True,
                        )
                        points = res.points
                    except Exception:
                        points = []

                if not points:
                    try:
                        res_scroll, _ = await self._client.scroll(
                            collection_name=target_col,
                            scroll_filter=filter_cond,
                            limit=limit,
                            with_payload=True,
                        )
                        points = res_scroll
                    except Exception:
                        points = []

                for pt in points:
                    payload = getattr(pt, "payload", {}) or {}
                    fp = payload.get("file_path") or payload.get("metadata", {}).get("file_path")
                    if workspace_root and fp and not _is_file_in_workspace(fp, workspace_root):
                        continue
                    text = extract_passage_text(payload)
                    if text:
                        skeleton_texts.append(text)
            except Exception as e:
                logger.debug(f"[Tier 3] Qdrant ast_skeleton retrieval error: {e}")

        # 2. Fallback to top-level AST symbols and file summaries from FalkorDB
        if not skeleton_texts and self._falkordb:
            try:
                target_graph = resolve_symbol_graph_for_collection(collection) or DEFAULT_SYMBOLS_GRAPH
                cypher = """
                MATCH (f:File)
                OPTIONAL MATCH (s:Symbol)-[d:DEFINED_IN]->(f)
                RETURN f.path AS file, f.summary AS summary,
                       collect({name: s.name, kind: s.kind, signature: d.signature})[..5] AS symbols
                LIMIT 10
                """
                res = self._falkordb.query(target_graph, cypher)
                if res and len(res) > 1 and res[1]:
                    falkor_lines = []
                    for row in res[1]:
                        f_path, f_summary, syms = row[0], row[1], row[2]
                        if workspace_root and f_path and not _is_file_in_workspace(f_path, workspace_root):
                            continue
                        falkor_lines.append(f"- **File:** `{f_path}`")
                        if f_summary:
                            falkor_lines.append(f"  - Summary: {f_summary}")
                        if syms and isinstance(syms, list):
                            for sym in syms[:4]:
                                if isinstance(sym, dict) and sym.get("name"):
                                    sig = sym.get("signature") or sym.get("name")
                                    falkor_lines.append(f"  - `{sig}` ({sym.get('kind', 'symbol')})")
                    if falkor_lines:
                        skeleton_texts.append("\n".join(falkor_lines))
            except Exception as e:
                logger.debug(f"[Tier 3] FalkorDB fallback error: {e}")

        if not skeleton_texts:
            return None

        combined = "\n\n".join(skeleton_texts).strip()
        if not combined:
            return None

        # Knapsack bound to budget
        curr_tokens = count_tokens(combined)
        if curr_tokens > budget:
            allowed_chars = max(40, budget * 4)
            combined = combined[:allowed_chars].rstrip()

        return combined if combined else None

    async def federated_query(
        self,
        query: str,
        token_budget: int = 1500,
        collection: Optional[str] = None,
        workspace_root: Optional[str] = None,
        detail_level: str = "balanced",
        project: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        Executes concurrent async retrieval across 4 memory tiers:
          - Tier 0: AST Symbol Seek via SymbolSeekEngine.seek_symbol
          - Tier 1: Hybrid Codebase Chunks via self.query(query, suppress_ast_signal=True)
          - Tier 2: Episodic History via AgentNativeEpisodicDriver.search
          - Tier 3: Architectural Overview via self._fetch_tier3_overview
        """
        if token_budget <= 0:
            return {
                "query": query,
                "symbolic_context": [],
                "code_chunks": [],
                "episodic_history": [],
                "architectural_overview": None,
                "total_estimated_tokens": 0,
            }

        # Auto-resolve workspace root and target symbol graph if collection provided
        if collection and not workspace_root:
            workspace_root = await resolve_workspace_root_for_collection(collection)

        target_sym_graph = resolve_symbol_graph_for_collection(collection)

        # Resolve target project scope:
        resolved_project: Optional[str] = None
        if project is not None:
            p_str = project.strip()
            if p_str.lower() == "all":
                resolved_project = "all"
            else:
                resolved_project = p_str
        else:
            if collection and collection.strip().lower() not in ("all", "default", "kortext_codebase", "cerebrum_codebase"):
                resolved_project = collection.strip()
            elif workspace_root:
                ws_name = Path(workspace_root).name.strip()
                if ws_name and ws_name.lower() not in ("all", "default", "", ".", "/"):
                    if ws_name.lower() in ("cortex", "cerebrum"):
                        resolved_project = "kortext"
                    else:
                        resolved_project = ws_name

            if not resolved_project:
                resolved_project = os.getenv("KORTEXT_PROJECT") or "kortext"

        # Detail Level Propagation Across All Tiers:
        dl = detail_level.lower().strip() if isinstance(detail_level, str) else "balanced"
        if dl == "compact":
            # Budget Split: 30% T0, 50% T1, 20% T2, 0% T3
            tier0_budget = max(10, int(token_budget * 0.30))
            tier1_budget = max(20, int(token_budget * 0.50))
            tier2_budget = max(10, token_budget - tier0_budget - tier1_budget)
            tier3_budget = 0
            ast_detail_level = "skeleton"
            max_tier1_chunks = 2
            max_tier2_facts = 2
        elif dl in ("comprehensive", "full"):
            # Budget Split: 25% T0, 35% T1, 15% T2, 25% T3
            tier0_budget = max(20, int(token_budget * 0.25))
            tier1_budget = max(50, int(token_budget * 0.35))
            tier2_budget = max(20, int(token_budget * 0.15))
            tier3_budget = max(0, token_budget - tier0_budget - tier1_budget - tier2_budget)
            ast_detail_level = "full"
            max_tier1_chunks = 10
            max_tier2_facts = 20
        else:
            # Balanced: Budget Split: 25% T0, 45% T1, 20% T2, 10% T3
            tier0_budget = max(20, int(token_budget * 0.25))
            tier1_budget = max(50, int(token_budget * 0.45))
            tier2_budget = max(20, int(token_budget * 0.20))
            tier3_budget = max(0, token_budget - tier0_budget - tier1_budget - tier2_budget)
            ast_detail_level = "interface"
            max_tier1_chunks = 5
            max_tier2_facts = 5

        def _estimate_item_tokens(item: Any) -> int:
            if isinstance(item, str):
                return count_tokens(item)
            elif isinstance(item, (dict, list)):
                return count_tokens(json.dumps(item))
            return count_tokens(str(item))

        # --- Tier 0: AST Symbol Seek ---
        async def _fetch_tier0() -> List[Dict[str, Any]]:
            try:
                candidates = extract_symbol_candidates(query)
                if not candidates:
                    return []

                async def _seek_one(sym: str) -> Optional[Any]:
                    try:
                        res = await asyncio.to_thread(
                            self.symbol_seek.seek_symbol,
                            sym,
                            detail_level=ast_detail_level,
                            graph_name=target_sym_graph,
                            workspace_root=workspace_root,
                        )
                    except TypeError:
                        res = await asyncio.to_thread(
                            self.symbol_seek.seek_symbol,
                            sym,
                            detail_level=ast_detail_level,
                        )
                    except Exception as e:
                        logger.warning(f"[Tier 0/SymbolSeek] Error seeking '{sym}': {e}")
                        return None

                    if isinstance(res, str):
                        try:
                            return json.loads(res)
                        except Exception:
                            return None
                    return res

                seek_results = await asyncio.gather(*[_seek_one(sym) for sym in candidates[:5]], return_exceptions=True)

                symbols: List[Dict[str, Any]] = []
                cur_tokens = 0
                for r in seek_results:
                    if not r or isinstance(r, Exception):
                        continue
                    if isinstance(r, dict):
                        if r.get("status") == "found":
                            matches = r.get("matches", [])
                            if isinstance(matches, list):
                                for m in matches:
                                    if workspace_root and isinstance(m, dict) and m.get("file"):
                                        if not _is_file_in_workspace(m.get("file"), workspace_root):
                                            continue
                                    cost = _estimate_item_tokens(m)
                                    if cur_tokens + cost <= tier0_budget or not symbols:
                                        symbols.append(m)
                                        cur_tokens += cost
                                    else:
                                        break
                        elif r.get("status") == "not_found":
                            continue
                        else:
                            if workspace_root and isinstance(r, dict) and r.get("file"):
                                if not _is_file_in_workspace(r.get("file"), workspace_root):
                                    continue
                            cost = _estimate_item_tokens(r)
                            if cur_tokens + cost <= tier0_budget or not symbols:
                                symbols.append(r)
                                cur_tokens += cost
                    elif isinstance(r, list):
                        for m in r:
                            if workspace_root and isinstance(m, dict) and m.get("file"):
                                if not _is_file_in_workspace(m.get("file"), workspace_root):
                                    continue
                            cost = _estimate_item_tokens(m)
                            if cur_tokens + cost <= tier0_budget or not symbols:
                                symbols.append(m)
                                cur_tokens += cost
                return symbols
            except Exception as e:
                logger.warning(f"[Tier 0/Symbols] Unhandled error: {e}")
                return []

        # --- Tier 1: Hybrid Codebase Chunks ---
        async def _fetch_tier1() -> List[str]:
            try:
                target_collection = collection or DEFAULT_COLLECTION
                try:
                    chunks = await self.query(
                        query,
                        limit=max_tier1_chunks,
                        collection=target_collection,
                        workspace_root=workspace_root,
                        suppress_ast_signal=True,
                    )
                except TypeError:
                    chunks = await self.query(
                        query,
                        limit=max_tier1_chunks,
                        collection=target_collection,
                        suppress_ast_signal=True,
                    )

                if not chunks or not isinstance(chunks, list):
                    return []

                if workspace_root:
                    filtered_chunks = []
                    for chunk in chunks:
                        c_str = chunk if isinstance(chunk, str) else str(chunk)
                        first_line = c_str.split("\n", 1)[0]
                        if first_line.startswith(("# File:", "File:", "// File:")):
                            f_path = first_line.split(":", 1)[1].strip().split(":")[0].strip()
                            if f_path and not _is_file_in_workspace(f_path, workspace_root):
                                continue
                        filtered_chunks.append(c_str)
                    chunks = filtered_chunks

                selected_chunks: List[str] = []
                cur_tokens = 0
                for chunk in chunks[:max_tier1_chunks]:
                    c_str = chunk if isinstance(chunk, str) else str(chunk)
                    if dl == "compact":
                        c_str = c_str[:256]
                    cost = count_tokens(c_str)
                    if cur_tokens + cost <= tier1_budget:
                        selected_chunks.append(c_str)
                        cur_tokens += cost
                    elif not selected_chunks and cost > tier1_budget:
                        max_chars = max(40, tier1_budget * 4)
                        if dl == "compact":
                            max_chars = min(256, max_chars)
                        truncated = c_str[:max_chars]
                        selected_chunks.append(truncated)
                        cur_tokens += count_tokens(truncated)
                        break
                    else:
                        break
                return selected_chunks
            except Exception as e:
                logger.warning(f"[Tier 1/Code] Unhandled error: {e}")
                return []

        # --- Tier 2: Episodic History ---
        async def _fetch_tier2() -> List[str]:
            try:
                raw_facts = await self.episodic.search(
                    query,
                    limit=max_tier2_facts,
                    project=resolved_project,
                    workspace_root=workspace_root,
                )

                if not raw_facts or not isinstance(raw_facts, list):
                    return []

                if collection or workspace_root:
                    keywords = []
                    if collection and collection.lower() not in ("all", "default", "kortext_codebase", "cerebrum_codebase"):
                        keywords.append(collection.lower())
                    if workspace_root:
                        ws_name = Path(workspace_root).name.lower()
                        if ws_name and ws_name not in ("all", "default"):
                            keywords.append(ws_name)
                    if keywords:
                        scoped_facts = [
                            f for f in raw_facts
                            if any(k in f.lower() for k in keywords)
                        ]
                        if scoped_facts:
                            raw_facts = scoped_facts + [f for f in raw_facts if f not in scoped_facts]

                selected_facts = apply_knapsack_mmr(
                    raw_facts,
                    query=query,
                    token_budget=tier2_budget,
                    lambda_param=0.7,
                )
                return selected_facts[:max_tier2_facts]
            except Exception as e:
                logger.warning(f"[Tier 2/Episodic] Unhandled error: {e}")
                return []

        # --- Tier 3: Architectural Overview ---
        async def _fetch_tier3() -> Optional[str]:
            if dl == "compact" or tier3_budget <= 0:
                return None
            try:
                return await self._fetch_tier3_overview(
                    workspace_root=workspace_root,
                    query=query,
                    budget=tier3_budget,
                    detail_level=dl,
                    collection=collection,
                )
            except Exception as e:
                logger.warning(f"[Tier 3/Overview] Unhandled error: {e}")
                return None

        # Execute all 4 tiers concurrently
        tier0_task = asyncio.create_task(_fetch_tier0())
        tier1_task = asyncio.create_task(_fetch_tier1())
        tier2_task = asyncio.create_task(_fetch_tier2())
        tier3_task = asyncio.create_task(_fetch_tier3())

        t0_res, t1_res, t2_res, t3_res = await asyncio.gather(
            tier0_task, tier1_task, tier2_task, tier3_task, return_exceptions=True
        )

        symbolic_context = t0_res if isinstance(t0_res, list) else []
        code_chunks = t1_res if isinstance(t1_res, list) else []
        episodic_history = t2_res if isinstance(t2_res, list) else []
        architectural_overview = t3_res if isinstance(t3_res, str) and t3_res.strip() else None

        t3_tokens = count_tokens(architectural_overview) if architectural_overview else 0
        total_tokens = (
            sum(_estimate_item_tokens(x) for x in symbolic_context)
            + sum(count_tokens(x) for x in code_chunks)
            + sum(count_tokens(x) for x in episodic_history)
            + t3_tokens
        )

        # Unified Knapsack Trimming:
        # Trim Tier 3 first if total exceeds token_budget,
        # followed by code chunks, episodic history, and symbol context.
        if total_tokens > token_budget and architectural_overview:
            excess = total_tokens - token_budget
            if t3_tokens <= excess:
                total_tokens -= t3_tokens
                architectural_overview = None
            else:
                keep_tokens = max(0, t3_tokens - excess)
                if keep_tokens < 15:
                    total_tokens -= t3_tokens
                    architectural_overview = None
                else:
                    architectural_overview = architectural_overview[:keep_tokens * 4].rstrip()
                    total_tokens = (
                        sum(_estimate_item_tokens(x) for x in symbolic_context)
                        + sum(count_tokens(x) for x in code_chunks)
                        + sum(count_tokens(x) for x in episodic_history)
                        + count_tokens(architectural_overview)
                    )

        while total_tokens > token_budget and (code_chunks or episodic_history or symbolic_context):
            if len(code_chunks) > 1:
                removed = code_chunks.pop()
                total_tokens -= count_tokens(removed)
            elif len(episodic_history) > 1:
                removed = episodic_history.pop()
                total_tokens -= count_tokens(removed)
            elif len(symbolic_context) > 1:
                removed = symbolic_context.pop()
                total_tokens -= _estimate_item_tokens(removed)
            elif code_chunks:
                t3_curr = count_tokens(architectural_overview) if architectural_overview else 0
                rem = max(10, token_budget - sum(_estimate_item_tokens(x) for x in symbolic_context) - sum(count_tokens(x) for x in episodic_history) - t3_curr)
                if rem < count_tokens(code_chunks[0]):
                    code_chunks[0] = code_chunks[0][:rem * 4]
                break
            else:
                break

            total_tokens = (
                sum(_estimate_item_tokens(x) for x in symbolic_context)
                + sum(count_tokens(x) for x in code_chunks)
                + sum(count_tokens(x) for x in episodic_history)
                + (count_tokens(architectural_overview) if architectural_overview else 0)
            )

        return {
            "query": query,
            "symbolic_context": symbolic_context,
            "code_chunks": code_chunks,
            "episodic_history": episodic_history,
            "architectural_overview": architectural_overview,
            "total_estimated_tokens": total_tokens,
        }

    async def close(self):
        """Closes the async Qdrant client connection."""
        if self._client:
            await self._client.close()
            self._client = None


_DEFAULT_RETRIEVAL_ENGINE: Optional[RetrievalEngine] = None


async def federated_query(
    query: str,
    token_budget: int = 1500,
    collection: Optional[str] = None,
    workspace_root: Optional[str] = None,
    detail_level: str = "balanced",
    project: Optional[str] = None,
    engine: Optional[RetrievalEngine] = None,
) -> Dict[str, Any]:
    """
    Module-level convenience wrapper for federated multi-tier retrieval.
    """
    global _DEFAULT_RETRIEVAL_ENGINE
    if engine is None:
        if _DEFAULT_RETRIEVAL_ENGINE is None:
            _DEFAULT_RETRIEVAL_ENGINE = RetrievalEngine()
        engine = _DEFAULT_RETRIEVAL_ENGINE
    return await engine.federated_query(
        query=query,
        token_budget=token_budget,
        collection=collection,
        workspace_root=workspace_root,
        detail_level=detail_level,
        project=project,
    )


_COLLECTION_WORKSPACE_CACHE: Dict[str, str] = {}


async def resolve_workspace_root_for_collection(collection_name: Optional[str]) -> Optional[str]:
    """
    Dynamically discovers the workspace root associated with a Qdrant collection
    by inspecting payload file paths, registered workspace roots, or common project directories.
    Ensures workspace root resolution always points to the exact project directory matching the target collection.
    """
    default_ws = os.getenv("WORKSPACE_ROOTS", str(Path.cwd()))
    if not collection_name or collection_name.lower() in ("all", "default"):
        return default_ws

    if collection_name in _COLLECTION_WORKSPACE_CACHE:
        return _COLLECTION_WORKSPACE_CACHE[collection_name]

    col_lower = collection_name.lower()

    # 1. Dynamic check for Kortext / Cortex root
    if col_lower in ("kortext", "kortext_codebase", "cerebrum", "cerebrum_codebase"):
        cortex_root = Path(__file__).resolve().parent.parent.parent
        if (cortex_root / "kortext").is_dir() or (cortex_root / "cerebrum").is_dir():
            _COLLECTION_WORKSPACE_CACHE[collection_name] = str(cortex_root)
            return str(cortex_root)

    # 2. Dynamic check for registered workspace roots or home directories
    env_roots = [Path(p.strip()) for p in os.getenv("WORKSPACE_ROOTS", "").split(",") if p.strip()]
    norm_col = col_lower.replace("_", "-")
    search_dirs = env_roots + [Path.home() / norm_col, Path.home() / col_lower, Path.cwd()]
    for cand in search_dirs:
        cand_norm = cand.name.lower().replace("_", "-")
        if cand.is_dir() and (cand_norm in norm_col or norm_col in cand_norm):
            _COLLECTION_WORKSPACE_CACHE[collection_name] = str(cand.resolve())
            return str(cand.resolve())

    # 3. Dynamic lookup via Qdrant point payload (inspecting file_path)
    qdrant_url = os.getenv("QDRANT_URL")
    if qdrant_url and qdrant_url.strip():
        client = None
        try:
            from qdrant_client import AsyncQdrantClient
            client = AsyncQdrantClient(url=qdrant_url.strip())
            pts, _ = await client.scroll(collection_name=collection_name, limit=5, with_payload=True)
            if pts:
                for pt in pts:
                    payload = getattr(pt, "payload", {}) or {}
                    fp = payload.get("file_path") or payload.get("metadata", {}).get("file_path")
                    if fp:
                        p = Path(fp).resolve()
                        # Check git root first across all parents
                        for parent in [p.parent] + list(p.parents):
                            if (parent / ".git").is_dir():
                                _COLLECTION_WORKSPACE_CACHE[collection_name] = str(parent)
                                return str(parent)
                        # Fallback to topmost directory below home
                        for parent in reversed(list(p.parents)):
                            if parent != Path.home() and parent != Path("/"):
                                _COLLECTION_WORKSPACE_CACHE[collection_name] = str(parent)
                                return str(parent)
        except Exception as e:
            logger.debug(f"Could not auto-resolve workspace root for collection '{collection_name}': {e}")
        finally:
            if client:
                try:
                    await client.close()
                except Exception:
                    pass
    else:
        # Native embedded mode: skip network client creation and use meta.json or default workspace root
        try:
            env_home = os.getenv("KORTEXT_HOME") or os.getenv("CEREBRUM_HOME")
            if env_home:
                kortext_home = Path(env_home)
                qdir = kortext_home / "qdrant"
            else:
                k_dir = Path.home() / ".kortext"
                c_dir = Path.home() / ".cerebrum"
                kortext_home = k_dir if k_dir.exists() or not c_dir.exists() else c_dir
                qdir = kortext_home / "qdrant"
            meta_file = qdir / "meta.json"
            if meta_file.is_file():
                meta_data = json.loads(meta_file.read_text(encoding="utf-8"))
                collections_map = meta_data.get("collections", {})
                if collection_name in collections_map:
                    col_meta = collections_map.get(collection_name, {})
                    if isinstance(col_meta, dict):
                        ws = (col_meta.get("metadata") or {}).get("workspace_root") or (col_meta.get("metadata") or {}).get("workspace")
                        if ws and Path(ws).is_dir():
                            _COLLECTION_WORKSPACE_CACHE[collection_name] = str(Path(ws).resolve())
                            return str(Path(ws).resolve())

                    # Check for collection-level meta.json
                    col_dir = qdir / "collection" / collection_name
                    if not col_dir.is_dir():
                        col_dir = qdir / "collections" / collection_name
                    if col_dir.is_dir():
                        col_meta_file = col_dir / "meta.json"
                        if col_meta_file.is_file():
                            try:
                                col_data = json.loads(col_meta_file.read_text(encoding="utf-8"))
                                ws = (col_data.get("metadata") or {}).get("workspace_root") or (col_data.get("metadata") or {}).get("workspace")
                                if ws and Path(ws).is_dir():
                                    _COLLECTION_WORKSPACE_CACHE[collection_name] = str(Path(ws).resolve())
                                    return str(Path(ws).resolve())
                            except Exception:
                                pass

                    sql_file = col_dir / "storage.sqlite" if col_dir.is_dir() else (cerebrum_home / "qdrant" / "collection" / collection_name / "storage.sqlite")
                    if sql_file.is_file():
                        try:
                            import sqlite3
                            conn = sqlite3.connect(f"file:{sql_file}?mode=ro", uri=True)
                            cur = conn.cursor()
                            cur.execute("SELECT point FROM points LIMIT 5")
                            rows = cur.fetchall()
                            conn.close()
                            for (blob,) in rows:
                                if not blob:
                                    continue
                                # Safe JSON payload inspection (no pickle)
                                if isinstance(blob, (bytes, bytearray)):
                                    try:
                                        pt_data = json.loads(blob.decode("utf-8"))
                                        payload = pt_data.get("payload") if isinstance(pt_data, dict) else None
                                        if payload and isinstance(payload, dict):
                                            fp = payload.get("file_path") or payload.get("metadata", {}).get("file_path")
                                            if fp:
                                                p = Path(fp).resolve()
                                                for parent in [p.parent] + list(p.parents):
                                                    if (parent / ".git").is_dir():
                                                        _COLLECTION_WORKSPACE_CACHE[collection_name] = str(parent)
                                                        return str(parent)
                                                for parent in reversed(list(p.parents)):
                                                    if parent != Path.home() and parent != Path("/"):
                                                        _COLLECTION_WORKSPACE_CACHE[collection_name] = str(parent)
                                                        return str(parent)
                                    except (UnicodeDecodeError, json.JSONDecodeError):
                                        pass

                                    # Safe string/path inspection without unpickling or code execution
                                    path_matches = re.findall(rb"(/[a-zA-Z0-9_\-\.]+/[a-zA-Z0-9_\-\.]+/[a-zA-Z0-9_\-\./]+)", blob)
                                    for raw_p in path_matches:
                                        try:
                                            cand = raw_p.decode("utf-8", errors="ignore")
                                            p = Path(cand).resolve()
                                            for parent in [p.parent] + list(p.parents):
                                                if (parent / ".git").is_dir():
                                                    _COLLECTION_WORKSPACE_CACHE[collection_name] = str(parent)
                                                    return str(parent)
                                            for parent in reversed(list(p.parents)):
                                                if parent != Path.home() and parent != Path("/"):
                                                    _COLLECTION_WORKSPACE_CACHE[collection_name] = str(parent)
                                                    return str(parent)
                                        except Exception:
                                            continue
                        except Exception:
                            pass
        except Exception as e:
            logger.debug(f"Could not resolve workspace root via meta.json for '{collection_name}': {e}")

    _COLLECTION_WORKSPACE_CACHE[collection_name] = default_ws
    return default_ws


def resolve_symbol_graph_for_collection(collection_name: Optional[str]) -> str:
    """
    Maps a collection name to its corresponding FalkorDB symbol/knowledge graph name.
    e.g. 'Antigravity_Docs' -> 'antigravity_docs', 'kortext_codebase' -> 'kortext_symbols'.
    """
    default_sym = os.getenv("KORTEXT_SYMBOLS_GRAPH", os.getenv("FALKORDB_SYMBOLS_GRAPH", "kortext_symbols"))
    if not collection_name:
        return default_sym
    col_lower = collection_name.lower()
    if "antigravity" in col_lower:
        return "antigravity_docs"
    elif "symbol" in col_lower:
        return collection_name
    elif col_lower in ("kortext", "kortext_codebase", "cerebrum", "cerebrum_codebase", "default"):
        return default_sym
    return f"{col_lower}_symbols"


