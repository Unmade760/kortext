"""
Truncation-Aware Adaptive Knee (TAA-k) trimming and passage text extraction for Kortext retrieval.
"""

from __future__ import annotations

import json
import logging
from typing import Any, Dict, List, Tuple

logger = logging.getLogger("kortext.retrieval.knee_trimmer")


def extract_passage_text(payload: Dict[str, Any]) -> str:
    """
    Extracts raw text content from Qdrant point payload across schemas.
    Checks 'text', '_node_content', 'document', and serializes payload as fallback.
    """
    if not payload:
        return ""
    if "text" in payload:
        return str(payload["text"])
    if "_node_content" in payload:
        try:
            nc = json.loads(payload["_node_content"])
            if "text" in nc:
                return str(nc["text"])
        except Exception as exc:
            logger.debug(f"Failed decoding _node_content JSON payload: {exc}")
    if "document" in payload:
        return str(payload["document"])
    try:
        return json.dumps(payload)
    except Exception as exc:
        logger.debug(f"Payload serialization fallback failed: {exc}")
        return str(payload)


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
