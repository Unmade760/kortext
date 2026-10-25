"""
Post-TAA-k cross-encoder reranker with strict latency bounding and deterministic offline fallback.
"""

from __future__ import annotations

import json
import logging
import os
import re
from collections import Counter
from typing import Any, Dict, List, Optional, Union

import httpx

logger = logging.getLogger("kortext.retrieval.reranker")

# Strict 250ms timeout for cross-encoder reranking
DEFAULT_RERANK_TIMEOUT_SECONDS: float = 0.250

# Lexical tie-breaker weights
DEFAULT_TOKEN_MATCH_WEIGHT: float = 0.10
DEFAULT_AST_HEADER_BONUS: float = 0.50
DEFAULT_SIGNATURE_MATCH_BONUS: float = 0.50


def is_ci_mode() -> bool:
    """Checks whether KORTEXT_CI_MODE (or CI_MODE/CI) is active in the environment."""
    return (
        os.getenv("KORTEXT_CI_MODE", os.getenv("CI_MODE", os.getenv("CI", "")))
        .strip()
        .lower()
        in ("1", "true", "yes")
    )


def extract_candidate_text(candidate: Union[Dict[str, Any], str]) -> str:
    """Extracts raw text representation from a candidate across various formats."""
    if isinstance(candidate, str):
        return candidate

    if isinstance(candidate, dict):
        for key in ("text", "passage", "document", "content"):
            val = candidate.get(key)
            if val is not None and isinstance(val, str):
                return val

        if "_node_content" in candidate:
            try:
                nc = json.loads(str(candidate["_node_content"]))
                if isinstance(nc, dict) and "text" in nc:
                    return str(nc["text"])
            except Exception:
                logger.debug("Suppressed non-fatal exception")

        if "document" in candidate:
            return str(candidate["document"])

    return str(candidate)


def compute_offline_score(
    query: str,
    candidate: Union[Dict[str, Any], str],
    token_weight: float = DEFAULT_TOKEN_MATCH_WEIGHT,
    ast_bonus: float = DEFAULT_AST_HEADER_BONUS,
    sig_bonus: float = DEFAULT_SIGNATURE_MATCH_BONUS,
) -> float:
    """
    Computes deterministic lexical tie-breaking score for offline fallback.
    Score = existing_score + (token_matches * token_weight) + AST header/signature bonuses.
    """
    text = extract_candidate_text(candidate)
    text_lower = text.lower()

    # Extract alphanumeric and code identifier tokens from query
    query_tokens = [tok.lower() for tok in re.findall(r"\b\w+\b", query) if len(tok) > 1]
    if not query_tokens:
        query_tokens = [query.strip().lower()] if query.strip() else []

    # 1. Exact token match count
    words_in_text = re.findall(r"\b\w+\b", text_lower)
    word_counts = Counter(words_in_text)
    token_matches = sum(word_counts[tok] for tok in query_tokens)

    # 2. AST header and signature bonus
    bonus = 0.0
    cand_dict = candidate if isinstance(candidate, dict) else {}
    cand_meta = cand_dict.get("metadata") if isinstance(cand_dict.get("metadata"), dict) else {}

    is_ast = (
        "### ast symbol:" in text_lower
        or "[ast]" in text_lower
        or cand_dict.get("tier") == "ast"
        or cand_meta.get("tier") == "ast"
    )
    if is_ast:
        bonus += ast_bonus

    # Signature line match bonus
    sig_matched = False
    for line in text.splitlines():
        line_lower = line.lower()
        if (
            "signature:" in line_lower
            or line_lower.strip().startswith("def ")
            or line_lower.strip().startswith("class ")
            or "fn " in line_lower
        ):
            if any(tok in line_lower for tok in query_tokens):
                sig_matched = True
                break

    if sig_matched:
        bonus += sig_bonus

    existing_score = 0.0
    if isinstance(candidate, dict):
        raw_score = candidate.get("score")
        if raw_score is None:
            raw_score = candidate.get("rrf_score")
        if isinstance(raw_score, (int, float)):
            existing_score = float(raw_score)

    blended_score = existing_score + (token_matches * token_weight) + bonus
    return round(blended_score, 6)


class RerankerEngine:
    """
    Cross-encoder reranker with strict latency bounding (250ms) and
    deterministic offline fallback.
    """

    def __init__(
        self,
        base_url: Optional[str] = None,
        model_name: Optional[str] = None,
        timeout_s: float = DEFAULT_RERANK_TIMEOUT_SECONDS,
    ):
        raw_base = base_url or os.getenv("RERANK_BASE_URL") or os.getenv("EMBED_BASE_URL", "http://127.0.0.1:8000/v1")
        self.base_url = raw_base.replace("://localhost", "://127.0.0.1").rstrip("/")
        if not self.base_url.endswith("/rerank"):
            self.rerank_url = f"{self.base_url}/rerank"
        else:
            self.rerank_url = self.base_url

        self.model_name = model_name or os.getenv(
            "RERANK_MODEL_NAME", "vserifsaglam--Qwen3-Reranker-4B-4bit-MLX"
        )
        self.timeout_s = timeout_s
        self.api_key = os.getenv("RERANK_API_KEY") or os.getenv("COHERE_API_KEY")
        self._client: Optional[httpx.AsyncClient] = None

    def _get_client(self) -> httpx.AsyncClient:
        if self._client is None or self._client.is_closed:
            self._client = httpx.AsyncClient(
                timeout=self.timeout_s,
                limits=httpx.Limits(max_keepalive_connections=5, max_connections=10),
            )
        return self._client

    def _normalize_candidates(
        self, candidates: List[Union[Dict[str, Any], str]]
    ) -> List[Dict[str, Any]]:
        """Ensures all candidate items are shallow-copied dictionaries with 'text' and 'score'."""
        normalized: List[Dict[str, Any]] = []
        for cand in candidates:
            if isinstance(cand, dict):
                item = dict(cand)
                if "text" not in item:
                    item["text"] = extract_candidate_text(item)
                if "score" not in item:
                    item["score"] = float(item.get("rrf_score", 0.0))
                normalized.append(item)
            else:
                normalized.append({
                    "text": str(cand),
                    "score": 0.0,
                })
        return normalized

    def _rerank_offline(
        self, query: str, candidates: List[Dict[str, Any]], top_k: int = 5
    ) -> List[Dict[str, Any]]:
        """Applies deterministic lexical tie-breaking and returns top_k candidates."""
        scored: List[Dict[str, Any]] = []
        for cand in candidates:
            item = dict(cand)
            score = compute_offline_score(query, item)
            item["rerank_score"] = score
            item["offline_fallback"] = True
            scored.append(item)

        scored.sort(key=lambda c: c.get("rerank_score", 0.0), reverse=True)
        return scored[:top_k]

    def rerank_sync(
        self,
        query: str,
        candidates: List[Union[Dict[str, Any], str]],
        top_k: int = 5,
    ) -> List[Dict[str, Any]]:
        """
        Synchronous wrapper for backward compatibility with synchronous scripts.
        Executes deterministic offline scoring.
        """
        return self._rerank_offline(
            query, self._normalize_candidates(candidates), top_k=top_k
        )

    async def rerank(
        self,
        query: str,
        candidates: List[Union[Dict[str, Any], str]],
        top_k: int = 5,
    ) -> List[Dict[str, Any]]:
        """
        Reranks retrieval candidates using remote cross-encoder (strict 250ms timeout)
        or falls back to deterministic offline scoring.

        Args:
            query: User search query or question.
            candidates: Scored passages or candidate dictionaries.
            top_k: Number of highest-ranked candidates to return.

        Returns:
            List of top_k candidate dictionaries sorted by rerank_score descending.
        """
        if not candidates:
            return []

        norm_candidates = self._normalize_candidates(candidates)

        # In CI mode, bypass remote calls entirely
        if is_ci_mode():
            return self._rerank_offline(query, norm_candidates, top_k=top_k)

        eval_docs = [cand["text"][:1200] for cand in norm_candidates]
        payload = {
            "model": self.model_name,
            "query": query,
            "documents": eval_docs,
        }
        headers = {"Content-Type": "application/json"}
        if self.api_key:
            headers["Authorization"] = f"Bearer {self.api_key}"

        try:
            client = self._get_client()
            resp = await client.post(self.rerank_url, json=payload, headers=headers)
            resp.raise_for_status()

            data = resp.json()
            results = data.get("results") if isinstance(data, dict) else None
            if results is None and isinstance(data, dict):
                results = data.get("data")
            if results is None and isinstance(data, list):
                results = data

            if not results or not isinstance(results, list):
                logger.debug("Reranker response missing results list. Falling back to offline tie-breaker.")
                return self._rerank_offline(query, norm_candidates, top_k=top_k)

            # Map relevance scores back to candidates
            scored: List[Dict[str, Any]] = []
            for r in results:
                if not isinstance(r, dict):
                    continue
                idx = r.get("index")
                if idx is None or not (0 <= idx < len(norm_candidates)):
                    continue
                cand = dict(norm_candidates[idx])
                rel_score = r.get("relevance_score")
                if rel_score is None:
                    rel_score = r.get("score", 0.0)
                cand["rerank_score"] = float(rel_score)
                cand["relevance_score"] = float(rel_score)
                cand["offline_fallback"] = False
                scored.append(cand)

            if not scored:
                return self._rerank_offline(query, norm_candidates, top_k=top_k)

            scored.sort(key=lambda c: c.get("rerank_score", 0.0), reverse=True)
            return scored[:top_k]

        except Exception as e:
            err_name = type(e).__name__
            logger.debug(
                f"Reranker unavailable ({err_name}: {e or 'timeout'}). "
                "Applying deterministic offline tie-breaker."
            )
            return self._rerank_offline(query, norm_candidates, top_k=top_k)

    async def close(self) -> None:
        """Closes the underlying httpx.AsyncClient session if active."""
        if self._client and not self._client.is_closed:
            await self._client.aclose()
            self._client = None
