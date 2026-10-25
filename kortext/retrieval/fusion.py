"""
5-Signal Reciprocal Rank Fusion (RRF), adaptive weights, and Knapsack MMR diversity.

Combines deterministic AST symbols, lexical BM25, dense semantics, associative HippoRAG,
and bi-temporal recency modulated by Stretched Weibull Decay.
"""

from __future__ import annotations

import json
import logging
import re
from typing import Any, Dict, List, Optional, Tuple, TypedDict

from kortext.chunking.token_utils import count_tokens
from kortext.retrieval.query_parser import is_ci_mode, is_symbolic_query
from kortext.retrieval.retention import (
    DEFAULT_FLOOR,
    compute_age_hours,
    compute_weibull_retention,
)

logger = logging.getLogger("kortext.retrieval.fusion")

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
    - If CI mode is enabled or dense_available=False: redistributes dense weight mass.
    - If suppress_ast_signal=True: zeros out AST weight and redistributes its mass.
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


def _extract_item_passage_and_meta(
    item: Any,
) -> Tuple[str, Optional[float], Optional[int], Dict[str, Any]]:
    """Normalizes candidate items into (passage, age_hours, importance, metadata)."""
    item_age: Optional[float] = None
    item_imp: Optional[int] = None
    item_meta_dict: Dict[str, Any] = {}

    if isinstance(item, str):
        return item, None, None, {}

    if isinstance(item, tuple):
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
                logger.debug("Suppressed non-fatal exception")
        return passage, item_age, item_imp, item_meta_dict

    if isinstance(item, dict):
        passage = str(item.get("text") or item.get("passage") or item.get("document") or item)
        item_meta_dict.update(item)
        if isinstance(item.get("metadata"), dict):
            item_meta_dict.update(item["metadata"])
        return passage, item_age, item_imp, item_meta_dict

    passage = getattr(item, "text", None) or getattr(item, "passage", str(item))
    for attr in ("age_hours", "delta_hours", "delta_t", "importance", "timestamp", "created_at", "valid_from"):
        val = getattr(item, attr, None)
        if val is not None:
            item_meta_dict[attr] = val
    item_metadata_attr = getattr(item, "metadata", None)
    if isinstance(item_metadata_attr, dict):
        item_meta_dict.update(item_metadata_attr)
    return passage, item_age, item_imp, item_meta_dict


def compute_length_penalty(passage: str, pivot_chars: int = 500, alpha: float = 0.5) -> float:
    """
    Computes the logarithmic length normalization factor ("Semantic Sponge" defense):
        LengthFactor = 1.0 / (1.0 + alpha * log2(max(1.0, len(passage) / pivot_chars)))
    Prevents overly verbose chunks or reports from crowding out surgical definitions.
    """
    if not passage:
        return 1.0
    import math

    char_len = len(passage)
    if char_len <= pivot_chars:
        return 1.0
    ratio = max(1.0, char_len / float(pivot_chars))
    penalty = 1.0 / (1.0 + alpha * math.log2(ratio))
    return max(0.40, min(1.0, penalty))


def has_exact_lexical_identifier_match(passage: str, query: Optional[str]) -> bool:
    """Checks whether the candidate passage contains an exact code identifier from the query."""
    if not query or not passage:
        return False
    idents = [
        tok for tok in re.findall(r"[A-Za-z_][A-Za-z0-9_]{2,}", query)
        if ("_" in tok or any(c.isupper() for c in tok[1:]))
    ]
    if not idents:
        return False
    return any(ident in passage for ident in idents)


def rank_candidates_rrf(
    signals: List[Tuple[List[Any], float]] | Dict[str, List[Any]],
    candidate_metadata: Optional[Dict[str, Dict[str, Any]]] = None,
    retention_weight: float = 1.0,
    weights: Optional[Dict[str, float]] = None,
    query: Optional[str] = None,
) -> List[Tuple[str, float]]:
    """
    Merges and scores candidates across retrieval tiers using
    Reciprocal Rank Fusion (RRF) modulated by Stretched Weibull Decay retention,
    logarithmic length normalization ("Semantic Sponge" defense), and Lexical Match Floor.

    Score per candidate:
        score(c) = sum_{tier} ( w_tier / (K_RRF + rank) ) * effective_retention(c) * length_penalty(c)
    """
    rrf_scores: Dict[str, float] = {}
    bm25_top_scores: Dict[str, float] = {}
    meta_lookup = dict(candidate_metadata) if candidate_metadata else {}

    if isinstance(signals, dict):
        active_weights = dict(weights) if weights is not None else dict(DEFAULT_FUSION_WEIGHTS)
        if is_ci_mode() or not signals.get("dense"):
            active_weights = redistribute_weights(active_weights, inactive_keys=["dense"])
        signal_list: List[Tuple[List[Any], float]] = [
            (items, active_weights.get(tier, 0.0)) for tier, items in signals.items()
        ]
        bm25_items = signals.get("bm25") or []
    else:
        signal_list = signals
        bm25_items = signal_list[1][0] if len(signal_list) > 1 else []

    for rank, b_item in enumerate(bm25_items[:3]):
        b_pass, _, _, _ = _extract_item_passage_and_meta(b_item)
        bm25_top_scores[b_pass] = (1.0 / (K_RRF + rank + 1))

    for items, weight in signal_list:
        for rank, item in enumerate(items):
            passage, item_age, item_imp, item_meta_dict = _extract_item_passage_and_meta(item)

            meta: Dict[str, Any] = dict(meta_lookup.get(passage, {}))
            meta.update(item_meta_dict)

            age_hours = item_age if item_age is not None else (
                meta.get("age_hours") or meta.get("delta_hours")
            )
            if age_hours is None and "delta_t" in meta and "lam" not in meta:
                raw_dt = meta["delta_t"]
                if isinstance(raw_dt, (int, float)):
                    age_hours = raw_dt if raw_dt < 1e5 else raw_dt / 3600.0

            if age_hours is None:
                ts = meta.get("timestamp") or meta.get("created_at") or meta.get("valid_from")
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
            len_mod = compute_length_penalty(passage) if meta.get("apply_length_penalty", len(passage) > 1200) else 1.0
            lex_boost = 1.15 if (query and has_exact_lexical_identifier_match(passage, query)) else 1.0
            score = (weight / (K_RRF + (rank + 1))) * effective_retention * len_mod * lex_boost
            rrf_scores[passage] = rrf_scores.get(passage, 0.0) + score

    if query and bm25_top_scores:
        for b_pass, b_base in bm25_top_scores.items():
            if b_pass in rrf_scores and has_exact_lexical_identifier_match(b_pass, query):
                rrf_scores[b_pass] = max(rrf_scores[b_pass], b_base * 0.92)

    if not rrf_scores:
        return []

    return sorted(rrf_scores.items(), key=lambda x: x[1], reverse=True)


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

            if current_tokens + cand_tokens > token_budget:
                continue

            cand_words = cand_word_sets[idx]
            redundancy = (
                max(token_sim(cand_words, sel_words) for sel_words in selected_word_sets)
                if selected_word_sets
                else 0.0
            )

            if redundancy >= diversity_threshold:
                continue

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
