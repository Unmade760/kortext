"""
Information Retrieval (IR) and Question Answering (QA) Evaluation Metrics.

Pure Python implementation with zero external dependencies (standard library only).
Includes:
- recall_at_k: Recall at rank cutoff k.
- precision_at_k: Precision at rank cutoff k.
- mean_reciprocal_rank: Reciprocal Rank (MRR component) for ranked retrieval.
- ndcg_at_k: Normalized Discounted Cumulative Gain at rank cutoff k (binary relevance).
- exact_match: Normalized exact match accuracy for text predictions.
- token_f1: Token-level overlap F1 score (harmonic mean of token precision and recall).
"""

from __future__ import annotations

from collections import Counter
import math
import string
from typing import List, Sequence


def normalize_text(text: str) -> str:
    """Normalize text for evaluation.

    Steps applied:
    1. Lowercase all characters.
    2. Strip punctuation characters (from string.punctuation).
    3. Collapse consecutive whitespace into single spaces and strip outer whitespace.

    Args:
        text: Input string to normalize.

    Returns:
        Normalized string.
    """
    if not text:
        return ""
    lowered = text.lower()
    exclude = set(string.punctuation)
    no_punc = "".join(ch for ch in lowered if ch not in exclude)
    return " ".join(no_punc.split())


def recall_at_k(retrieved: List[str] | Sequence[str], gold: List[str] | Sequence[str], k: int) -> float:
    """Compute Recall@k for retrieved document identifiers against gold identifiers.

    Recall@k measures the fraction of relevant documents present in the top-k retrieved list.

    Args:
        retrieved: Ranked sequence of retrieved document IDs.
        gold: Sequence of gold relevant document IDs.
        k: Rank cutoff threshold.

    Returns:
        Recall score in [0.0, 1.0].
    """
    if k <= 0 or not retrieved or not gold:
        return 0.0
    gold_set = set(gold)
    if not gold_set:
        return 0.0
    top_k = retrieved[:k]
    relevant_retrieved = set(top_k) & gold_set
    return len(relevant_retrieved) / len(gold_set)


def precision_at_k(retrieved: List[str] | Sequence[str], gold: List[str] | Sequence[str], k: int) -> float:
    """Compute Precision@k for retrieved document identifiers against gold identifiers.

    Standard Information Retrieval definition:
        Precision@k = |{relevant documents} ∩ {top-k retrieved documents}| / k.

    Args:
        retrieved: Ranked sequence of retrieved document IDs.
        gold: Sequence of gold relevant document IDs.
        k: Rank cutoff threshold.

    Returns:
        Precision score in [0.0, 1.0].
    """
    if k <= 0 or not retrieved or not gold:
        return 0.0
    gold_set = set(gold)
    if not gold_set:
        return 0.0
    top_k = retrieved[:k]
    relevant_retrieved = set(top_k) & gold_set
    return len(relevant_retrieved) / float(k)


def mean_reciprocal_rank(retrieved: List[str] | Sequence[str], gold: List[str] | Sequence[str]) -> float:
    """Compute Reciprocal Rank (RR) for a ranked retrieval result.

    Returns 1.0 / rank of the first relevant document in the retrieved list (1-indexed).
    If no relevant document is retrieved, returns 0.0.

    Args:
        retrieved: Ranked sequence of retrieved document IDs.
        gold: Sequence of gold relevant document IDs.

    Returns:
        Reciprocal rank score in [0.0, 1.0].
    """
    if not retrieved or not gold:
        return 0.0
    gold_set = set(gold)
    if not gold_set:
        return 0.0
    for rank, doc_id in enumerate(retrieved, start=1):
        if doc_id in gold_set:
            return 1.0 / float(rank)
    return 0.0


def ndcg_at_k(retrieved: List[str] | Sequence[str], gold: List[str] | Sequence[str], k: int) -> float:
    """Compute Normalized Discounted Cumulative Gain at k (NDCG@k) with binary relevance.

    DCG@k = sum_{i=1}^{min(k, |retrieved|)} rel_i / log2(i + 1)
    IDCG@k = sum_{j=1}^{min(k, |gold|)} 1.0 / log2(j + 1)
    NDCG@k = DCG@k / IDCG@k

    Args:
        retrieved: Ranked sequence of retrieved document IDs.
        gold: Sequence of gold relevant document IDs.
        k: Rank cutoff threshold.

    Returns:
        NDCG@k score in [0.0, 1.0].
    """
    if k <= 0 or not retrieved or not gold:
        return 0.0
    gold_set = set(gold)
    if not gold_set:
        return 0.0

    # Ideal DCG with binary relevance (all relevant documents ranked at the top)
    num_ideal = min(k, len(gold_set))
    if num_ideal == 0:
        return 0.0
    idcg = sum(1.0 / math.log2(j + 1) for j in range(1, num_ideal + 1))
    if idcg == 0.0:
        return 0.0

    # Discounted cumulative gain of actual retrieved list up to rank k
    dcg = 0.0
    seen = set()
    for rank, doc_id in enumerate(retrieved[:k], start=1):
        if doc_id in gold_set and doc_id not in seen:
            seen.add(doc_id)
            dcg += 1.0 / math.log2(rank + 1)

    return dcg / idcg


def exact_match(prediction: str, gold: str) -> float:
    """Compute Exact Match (EM) score between prediction and gold strings.

    Normalizes both strings by lowercasing, stripping punctuation, and collapsing
    consecutive whitespace characters before comparison.

    Args:
        prediction: Candidate prediction string.
        gold: Ground-truth reference string.

    Returns:
        1.0 if normalized prediction matches normalized gold, 0.0 otherwise.
    """
    norm_pred = normalize_text(prediction)
    norm_gold = normalize_text(gold)
    return 1.0 if norm_pred == norm_gold else 0.0


def token_f1(prediction: str, gold: str) -> float:
    """Compute token-level F1 score between prediction and gold strings.

    Normalizes both strings, splits them into whitespace-delimited tokens, and computes
    multiset token overlap precision and recall.

    Args:
        prediction: Candidate prediction string.
        gold: Ground-truth reference string.

    Returns:
        F1 score in [0.0, 1.0].
    """
    pred_tokens = normalize_text(prediction).split()
    gold_tokens = normalize_text(gold).split()

    if not pred_tokens and not gold_tokens:
        return 1.0
    if not pred_tokens or not gold_tokens:
        return 0.0

    pred_counter = Counter(pred_tokens)
    gold_counter = Counter(gold_tokens)
    overlap = pred_counter & gold_counter
    num_same = sum(overlap.values())

    if num_same == 0:
        return 0.0

    precision = num_same / len(pred_tokens)
    recall = num_same / len(gold_tokens)
    return (2.0 * precision * recall) / (precision + recall)
