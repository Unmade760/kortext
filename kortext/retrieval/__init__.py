"""Retrieval package: Qdrant, LlamaIndex, and Qwen3 reranker."""
from typing import Any
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

_ENGINE_ATTRS = {
    "RetrievalEngine",
    "federated_query",
    "FederatedRetrievalResult",
    "apply_knapsack_mmr",
    "resolve_workspace_root_for_collection",
    "resolve_symbol_graph_for_collection",
}


def __getattr__(name: str) -> Any:
    if name == "discover_vector_collections":
        from .discovery import discover_vector_collections
        return discover_vector_collections
    if name == "RerankerEngine":
        from .reranker import RerankerEngine
        return RerankerEngine
    if name in _ENGINE_ATTRS:
        from . import engine as _engine
        return getattr(_engine, name)
    raise AttributeError(f"module 'kortext.retrieval' has no attribute {name!r}")

