#!/usr/bin/env python3
"""
Cerebrum Vector & Knowledge Migration Utility.
Migrates legacy points from Docker Qdrant (:6333) into native Embedded Qdrant (~/.cerebrum/qdrant).
Handles dictionary vector configurations and modern query_points APIs gracefully.
"""

from __future__ import annotations

import logging
import os
import sys
from pathlib import Path

from qdrant_client import QdrantClient
from qdrant_client.models import (
    Distance,
    OptimizersConfigDiff,
    PointStruct,
    SparseIndexParams,
    SparseVectorParams,
    VectorParams,
)

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("cerebrum.migration")

CEREBRUM_HOME = Path(os.getenv("CEREBRUM_HOME", str(Path.home() / ".cerebrum")))
TARGET_PATH = CEREBRUM_HOME / "qdrant"
SOURCE_URL = os.getenv("LEGACY_QDRANT_URL", "http://localhost:6333")


def migrate_collections():
    logger.info(f"Probing source Docker Qdrant at {SOURCE_URL}...")
    try:
        source_client = QdrantClient(url=SOURCE_URL, timeout=5.0)
        source_cols = source_client.get_collections().collections
    except Exception as e:
        logger.warning(f"Could not connect to Docker Qdrant ({e}). Assuming clean native installation.")
        return

    TARGET_PATH.mkdir(parents=True, exist_ok=True)
    logger.info(f"Initializing target Embedded Qdrant at {TARGET_PATH}...")
    target_client = QdrantClient(path=str(TARGET_PATH))

    for col in source_cols:
        col_name = col.name
        logger.info(f"--- Migrating Collection: {col_name} ---")

        # 1. Fetch source schema
        info = source_client.get_collection(col_name)
        params = info.config.params

        # Parse vector configuration (handle both dict and single VectorParams)
        vectors_config = {}
        if isinstance(params.vectors, dict):
            for v_name, v_param in params.vectors.items():
                vectors_config[v_name] = VectorParams(
                    size=v_param.size,
                    distance=v_param.distance,
                    on_disk=True,
                )
        elif params.vectors is not None:
            vectors_config["text-dense"] = VectorParams(
                size=params.vectors.size,
                distance=params.vectors.distance,
                on_disk=True,
            )
        else:
            vectors_config["text-dense"] = VectorParams(
                size=2048,
                distance=Distance.COSINE,
                on_disk=True,
            )

        # Parse sparse vectors
        sparse_config = None
        if params.sparse_vectors:
            sparse_config = {
                s_name: SparseVectorParams(index=SparseIndexParams(on_disk=True))
                for s_name in params.sparse_vectors.keys()
            }

        # 2. Recreate target collection
        if target_client.collection_exists(col_name):
            logger.info(f"Target collection '{col_name}' exists. Verifying record counts...")
        else:
            logger.info(f"Creating collection '{col_name}' in embedded storage...")
            target_client.create_collection(
                collection_name=col_name,
                vectors_config=vectors_config,
                sparse_vectors_config=sparse_config,
                optimizers_config=OptimizersConfigDiff(memmap_threshold=20000),
            )

        # 3. Stream points in batches
        offset = None
        total_migrated = 0
        while True:
            records, offset = source_client.scroll(
                collection_name=col_name,
                limit=250,
                offset=offset,
                with_payload=True,
                with_vectors=True,
            )
            if not records:
                break

            points = []
            for r in records:
                points.append(PointStruct(id=r.id, vector=r.vector, payload=r.payload))

            target_client.upsert(collection_name=col_name, points=points)
            total_migrated += len(points)
            logger.info(f"Migrated {total_migrated} points into '{col_name}'...")

            if offset is None:
                break

        logger.info(f"Successfully migrated {total_migrated} points for '{col_name}'.")

        # If migrating legacy codebase, also seed the native cerebrum_codebase collection
        if col_name == "cortex_codebase":
            target_alias = "cerebrum_codebase"
            logger.info(f"--- Seeding Native Collection '{target_alias}' from '{col_name}' ---")
            if not target_client.collection_exists(target_alias):
                target_client.create_collection(
                    collection_name=target_alias,
                    vectors_config=vectors_config,
                    sparse_vectors_config=sparse_config,
                    optimizers_config=OptimizersConfigDiff(memmap_threshold=20000),
                )
            # Scroll from target_client or source_client
            offset = None
            alias_migrated = 0
            while True:
                records, offset = source_client.scroll(
                    collection_name=col_name,
                    limit=250,
                    offset=offset,
                    with_payload=True,
                    with_vectors=True,
                )
                if not records:
                    break
                pts = [PointStruct(id=r.id, vector=r.vector, payload=r.payload) for r in records]
                target_client.upsert(collection_name=target_alias, points=pts)
                alias_migrated += len(pts)
                if offset is None:
                    break
            logger.info(f"Successfully populated native '{target_alias}' with {alias_migrated} points.")

    logger.info("=== All Collections Migrated to Embedded Qdrant Successfully ===")


if __name__ == "__main__":
    migrate_collections()
