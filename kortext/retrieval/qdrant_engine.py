"""
Kortext Modern Embedded Qdrant Storage Engine.
Uses in-process Rust engine (Zero-Docker) and modern query_points / Prefetch APIs.
"""

from __future__ import annotations

import logging
import os
from pathlib import Path
from typing import Any, Dict, List, Optional

from qdrant_client import QdrantClient
from qdrant_client.models import (
    Distance,
    Fusion,
    FusionQuery,
    HnswConfigDiff,
    OptimizersConfigDiff,
    PointStruct,
    Prefetch,
    SparseIndexParams,
    SparseVector,
    SparseVectorParams,
    VectorParams,
)

logger = logging.getLogger("kortext.qdrant")


from kortext._home import KORTEXT_HOME

CEREBRUM_HOME = KORTEXT_HOME
DEFAULT_QDRANT_PATH = KORTEXT_HOME / "qdrant"
if not (os.getenv("KORTEXT_HOME") or os.getenv("CEREBRUM_HOME")) and not DEFAULT_QDRANT_PATH.exists() and (Path.home() / ".cerebrum" / "qdrant").exists():
    DEFAULT_QDRANT_PATH = Path.home() / ".cerebrum" / "qdrant"


from kortext._qdrant import get_qdrant_client


class EmbeddedQdrantEngine:
    """Manages in-process embedded Qdrant lifecycle and modern hybrid vector search."""

    def __init__(
        self,
        storage_path: Optional[Path] = None,
        url: Optional[str] = None,
    ):
        self.client = get_qdrant_client(url=url, storage_path=storage_path)

    def resolve_collection_name(self, collection_name: str) -> str:
        """Accept both 'kortext' and 'cerebrum' names for seamless backward-compatibility."""
        try:
            cols = [c.name for c in self.client.get_collections().collections]
            if collection_name in cols:
                return collection_name
            if collection_name in ("kortext_codebase", "kortext") and "cerebrum_codebase" in cols:
                return "cerebrum_codebase"
            if collection_name in ("cerebrum_codebase", "cerebrum") and "kortext_codebase" in cols:
                return "kortext_codebase"
        except Exception:
            pass
        return collection_name

    def ensure_collection(self, collection_name: str, embed_dim: int = 2048):
        """Ensures dual-vector schema with dense MRL and sparse BM25 configurations."""
        resolved = self.resolve_collection_name(collection_name)
        if self.client.collection_exists(resolved):
            return

        logger.info(f"Provisioning dual-vector collection: {resolved}")
        self.client.create_collection(
            collection_name=resolved,
            vectors_config={
                "text-dense": VectorParams(
                    size=embed_dim,
                    distance=Distance.COSINE,
                    on_disk=True,
                    hnsw_config=HnswConfigDiff(m=16, ef_construct=100, on_disk=True),
                )
            },
            sparse_vectors_config={
                "text-sparse-new": SparseVectorParams(
                    index=SparseIndexParams(on_disk=True)
                )
            },
            optimizers_config=OptimizersConfigDiff(
                default_segment_number=2,
                memmap_threshold=20000,
            ),
        )

    def upsert_points(
        self,
        collection_name: str,
        points: List[PointStruct],
    ):
        """Upserts points into collection."""
        resolved = self.resolve_collection_name(collection_name)
        self.ensure_collection(resolved)
        self.client.upsert(collection_name=resolved, points=points)

    def hybrid_search(
        self,
        collection_name: str,
        dense_vector: List[float],
        sparse_indices: List[int],
        sparse_values: List[float],
        limit: int = 15,
    ) -> List[Dict[str, Any]]:
        """
        Executes modern RRF hybrid search via query_points and Prefetch objects.
        """
        resolved = self.resolve_collection_name(collection_name)
        if not self.client.collection_exists(resolved):
            return []

        response = self.client.query_points(
            collection_name=resolved,
            prefetch=[
                Prefetch(
                    query=dense_vector,
                    using="text-dense",
                    limit=limit * 2,
                ),
                Prefetch(
                    query=SparseVector(indices=sparse_indices, values=sparse_values),
                    using="text-sparse-new",
                    limit=limit * 2,
                ),
            ],
            query=FusionQuery(fusion=Fusion.RRF),
            limit=limit,
            with_payload=True,
        )

        results = []
        for p in response.points:
            results.append({
                "id": p.id,
                "score": p.score,
                "payload": p.payload or {},
            })
        return results


# Alias for standard naming and compatibility
QdrantEngine = EmbeddedQdrantEngine
