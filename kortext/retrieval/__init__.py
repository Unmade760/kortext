"""Retrieval package: Qdrant, LlamaIndex, and Qwen3 reranker."""
from .discovery import discover_vector_collections
from .engine import (
    RetrievalEngine,
    federated_query,
    FederatedRetrievalResult,
    apply_knapsack_mmr,
    resolve_workspace_root_for_collection,
    resolve_symbol_graph_for_collection,
)
from .reranker import RerankerEngine
from .retention import compute_weibull_retention, compute_age_hours

__all__ = [
    "RetrievalEngine",
    "RerankerEngine",
    "discover_vector_collections",
    "compute_weibull_retention",
    "compute_age_hours",
    "federated_query",
    "FederatedRetrievalResult",
    "apply_knapsack_mmr",
    "resolve_workspace_root_for_collection",
    "resolve_symbol_graph_for_collection",
]
