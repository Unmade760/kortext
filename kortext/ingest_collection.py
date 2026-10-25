"""Qdrant hybrid collection setup helper for Kortext ingestion."""
from __future__ import annotations

import logging
import os
import sys
from typing import Optional

from qdrant_client import AsyncQdrantClient
from qdrant_client.http import models as qmodels

from kortext._env import get_qdrant_collection
from kortext.cache import IngestCache
from kortext.embeddings import get_dense_embedder

logger = logging.getLogger(__name__)


def _resolve_dense_embedder():
    ingest_mod = sys.modules.get("kortext.ingest")
    if ingest_mod is not None and hasattr(ingest_mod, "get_dense_embedder"):
        return ingest_mod.get_dense_embedder()
    return get_dense_embedder()


async def setup_collection(
    client: AsyncQdrantClient,
    collection: Optional[str] = None,
    embed_dim: Optional[int] = None,
    cache: Optional[IngestCache] = None,
    force: bool = False,
) -> int:
    """
    Ensures Qdrant collection exists with dense + sparse BM25 support.
    Checks existing collection's vector size via client.get_collection(...).
    Never deletes a populated existing hybrid collection on dimension mismatch unless
    force=True (--force) or KORTEXT_ALLOW_COLLECTION_RESET=1 is explicitly set.
    Empty collections (points_count == 0) are automatically resized to target_dim.
    Returns the resolved collection dimension.
    """
    collection = collection or get_qdrant_collection()
    embedder = _resolve_dense_embedder()
    target_dim = embed_dim
    if target_dim is None:
        env_dim = os.getenv("EMBED_DIMENSION")
        target_dim = int(env_dim) if env_dim else getattr(embedder, "dimension", 384)

    collections = await client.get_collections()
    existing = [c.name for c in collections.collections]

    needs_recreate = False
    if collection in existing:
        try:
            col_info = await client.get_collection(collection_name=collection)
            has_sparse = (
                col_info.config.params.sparse_vectors is not None
                and "text-sparse-new" in col_info.config.params.sparse_vectors
            )
            existing_dim = None
            vec_params = getattr(col_info.config.params, "vectors", None)
            if isinstance(vec_params, dict) and "text-dense" in vec_params:
                td = vec_params["text-dense"]
                if hasattr(td, "size") and isinstance(td.size, int):
                    existing_dim = td.size
            elif hasattr(vec_params, "size") and isinstance(vec_params.size, int):
                existing_dim = vec_params.size

            if not has_sparse:
                logger.info(f"[Kortext Ingest] Upgrading collection '{collection}' to hybrid dense + sparse (BM25)...")
                await client.delete_collection(collection)
                if cache is not None:
                    cache.clear_collection(collection)
                needs_recreate = True
            elif existing_dim is not None and existing_dim != target_dim:
                pts_cnt = getattr(col_info, "points_count", None)
                force_reset = force or os.getenv("KORTEXT_ALLOW_COLLECTION_RESET", "0").strip().lower() in ("1", "true", "yes")
                # Protect populated collections (where points_count > 0) unless force=True or KORTEXT_ALLOW_COLLECTION_RESET=1
                if not force_reset and isinstance(pts_cnt, int) and pts_cnt > 0:
                    logger.warning(
                        f"[Kortext Ingest] Dimension mismatch on '{collection}' (existing={existing_dim}, embedder={target_dim}). "
                        f"Preserving existing collection ({pts_cnt} points) to prevent destructive index wipe on embedder fallback. "
                        f"Pass --force (or KORTEXT_ALLOW_COLLECTION_RESET=1) to recreate."
                    )
                    return existing_dim
                logger.info(
                    f"[Kortext Ingest] Recreating collection '{collection}' due to dimension change "
                    f"({existing_dim} -> {target_dim})..."
                )
                await client.delete_collection(collection)
                if cache is not None:
                    cache.clear_collection(collection)
                needs_recreate = True
        except Exception as exc:
            logger.warning(f"[Kortext Ingest] Warning checking collection info for '{collection}': {exc}")

    if collection not in existing or needs_recreate:
        await client.create_collection(
            collection_name=collection,
            vectors_config={"text-dense": qmodels.VectorParams(size=target_dim, distance=qmodels.Distance.COSINE)},
            sparse_vectors_config={"text-sparse-new": qmodels.SparseVectorParams()},
        )
        logger.info(f"[Kortext Ingest] Created hybrid collection '{collection}' (dense dim={target_dim} + sparse BM25)")
    else:
        logger.info(f"[Kortext Ingest] Using existing hybrid collection '{collection}' (upsert mode)")

    return target_dim
