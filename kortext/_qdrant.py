"""
Centralized Qdrant Client Factory and Custody Management for Kortext.

Enforces Sole Custodian Invariant:
- Production runtimes and subagents connect via Qdrant HTTP/gRPC.
- Direct embedded storage (QdrantClient(path=...)) is strictly isolated
  to explicit storage_path configurations (e.g. test fixtures).
"""

from __future__ import annotations

import logging
import socket
from pathlib import Path
from typing import Optional
from urllib.parse import urlparse

import httpx
from qdrant_client import AsyncQdrantClient, QdrantClient

from kortext._env import get_qdrant_url

logger = logging.getLogger("kortext.qdrant")

__all__ = [
    "get_qdrant_client",
    "get_sync_qdrant_client",
    "get_async_qdrant_client",
    "is_qdrant_online",
]


def get_qdrant_client(
    url: Optional[str] = None,
    storage_path: Optional[Path | str] = None,
    timeout: float = 5.0,
) -> QdrantClient:
    """
    Centralize Qdrant client lifecycle and enforce Sole Custodian Invariant.

    Resolution:
    1. If `url` is provided, connect via QdrantClient(url=url, timeout=timeout).
    2. If `storage_path` is explicitly provided, instantiate isolated Embedded Qdrant.
    3. Otherwise, use get_qdrant_url() from kortext._env and connect via HTTP.
    """
    if url:
        logger.info("Connecting to remote Qdrant at %s", url)
        return QdrantClient(url=url, timeout=timeout)

    if storage_path is not None:
        p = Path(storage_path)
        p.mkdir(parents=True, exist_ok=True)
        logger.info("Initializing isolated Embedded Qdrant at %s", p)
        return QdrantClient(path=str(p))

    resolved_url = get_qdrant_url()
    logger.info("Connecting to Qdrant at %s", resolved_url)
    return QdrantClient(url=resolved_url, timeout=timeout)


get_sync_qdrant_client = get_qdrant_client


def get_async_qdrant_client(
    url: Optional[str] = None,
    timeout: float = 5.0,
) -> AsyncQdrantClient:
    """Instantiate AsyncQdrantClient with url or get_qdrant_url()."""
    target_url = url or get_qdrant_url()
    logger.info("Connecting async Qdrant client at %s", target_url)
    return AsyncQdrantClient(url=target_url, timeout=timeout)


def is_qdrant_online(
    url: Optional[str] = None,
    timeout: float = 1.0,
) -> bool:
    """
    Quick boolean health check for Qdrant service using HTTP or socket probe.
    """
    target_url = (url or get_qdrant_url()).rstrip("/")
    if not target_url.startswith(("http://", "https://")):
        target_url = f"http://{target_url}"

    probe_url = target_url.replace("://localhost", "://127.0.0.1")

    # 1. HTTP Probe
    try:
        with httpx.Client(timeout=timeout) as client:
            resp = client.get(f"{probe_url}/healthz")
            if resp.status_code < 500:
                return True
            resp = client.get(f"{probe_url}/collections")
            return resp.status_code < 500
    except Exception:
        pass

    # 2. TCP Socket Probe fallback
    try:
        parsed = urlparse(target_url)
        host = parsed.hostname or "127.0.0.1"
        port = parsed.port or 6333
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.settimeout(timeout)
        result = sock.connect_ex((host, port))
        sock.close()
        return result == 0
    except Exception:
        return False
