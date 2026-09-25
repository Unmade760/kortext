"""
Cerebrum Modern Embedded Qdrant Storage Engine.
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

logger = logging.getLogger("cerebrum.qdrant")

CEREBRUM_HOME = Path(os.getenv("CEREBRUM_HOME", str(Path.home() / ".cerebrum")))
DEFAULT_QDRANT_PATH = CEREBRUM_HOME / "qdrant"


class EmbeddedQdrantEngine:
    """Manages in-process embedded Qdrant lifecycle and modern hybrid vector search."""

    def __init__(
        self,
        storage_path: Optional[Path] = None,
        url: Optional[str] = None,
    ):
        if url:
            logger.info(f"Connecting to remote Qdrant at {url}")
            self.client = QdrantClient(url=url)
        elif storage_path is not None:
            storage_path = Path(storage_path)
            storage_path.mkdir(parents=True, exist_ok=True)
            logger.info(f"Initializing native Embedded Qdrant at {storage_path}")
            self.client = QdrantClient(path=str(storage_path))
        elif os.getenv("QDRANT_URL"):
            q_url = os.getenv("QDRANT_URL")
            logger.info(f"Connecting to remote Qdrant at {q_url}")
            self.client = QdrantClient(url=q_url)
        else:
            default_path = DEFAULT_QDRANT_PATH
            default_path.mkdir(parents=True, exist_ok=True)
            logger.info(f"Initializing native Embedded Qdrant at default path {default_path}")
            self.client = QdrantClient(path=str(default_path))

    def ensure_collection(self, collection_name: str, embed_dim: int = 2048):
        """Ensures dual-vector schema with dense MRL and sparse BM25 configurations."""
        if self.client.collection_exists(collection_name):
            return

        logger.info(f"Provisioning dual-vector collection: {collection_name}")
        self.client.create_collection(
            collection_name=collection_name,
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
        self.ensure_collection(collection_name)
        self.client.upsert(collection_name=collection_name, points=points)

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
        if not self.client.collection_exists(collection_name):
            return []

        response = self.client.query_points(
            collection_name=collection_name,
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
