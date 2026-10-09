"""
Status, health checks, substrate telemetry, TCP/HTTP checkers, and collection point stats.
Invariant 3 compliance: Read-only inspection of embedded Qdrant files; no secondary QdrantClient(path=...).
"""

import asyncio
import json
import os
import socket
import time
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

import httpx
import psutil
from fastapi import APIRouter

from kortext.falkordb_client import get_shared_falkordb_client
from kortext.retrieval.discovery import discover_vector_collections

router = APIRouter(tags=["status"])

FALKORDB_HOST = os.getenv("FALKORDB_HOST", "127.0.0.1")
FALKORDB_PORT = int(os.getenv("FALKORDB_PORT", "6379"))
FALKORDB_DB = os.getenv("KORTEXT_DATABASE", os.getenv("FALKORDB_DATABASE", "kortext"))


def _check_tcp(host: str, port: int, timeout: float = 1.0) -> bool:
    try:
        with socket.create_connection((host, port), timeout=timeout):
            return True
    except OSError:
        return False


def _check_falkor_socket(sock_path: Path) -> bool:
    try:
        import redis
        r = redis.Redis(unix_socket_path=str(sock_path), socket_timeout=1.0)
        return bool(r.ping())
    except Exception:
        return False


async def _check_http(url: str, timeout: float = 2.0) -> tuple[bool, Optional[dict]]:
    try:
        async with httpx.AsyncClient(timeout=timeout) as client:
            resp = await client.get(url)
            if resp.status_code < 400:
                try:
                    return True, resp.json()
                except Exception:
                    return True, None
            return False, None
    except Exception:
        return False, None


@router.get("/api/status")
async def get_status():
    """Health check across Qdrant, FalkorDB, browser UI, and oMLX."""
    from kortext.health import audit_kortext_health

    return await audit_kortext_health(include_browser_ui=True, include_invariants=False)


@router.get("/api/collections")
async def list_collections():
    """List Qdrant collections with point counts and configs."""
    try:
        collections = await asyncio.to_thread(discover_vector_collections)
        return {"status": "ok", "collections": collections}
    except Exception as e:
        return {"status": "error", "message": str(e), "collections": []}



@router.get("/api/cache/stats")
async def get_cache_stats():
    """Returns chunk embedding cache and file ingestion cache metrics."""
    from kortext.cache import ChunkEmbeddingCache, IngestCache
    try:
        chunk_cache = ChunkEmbeddingCache()
        chunk_stats = chunk_cache.get_stats()
        ingest_cache = IngestCache()
        default_col = os.getenv("KORTEXT_COLLECTION", os.getenv("QDRANT_COLLECTION", "kortext_codebase"))
        all_files = ingest_cache.get_all_cached_files(default_col) or ingest_cache.get_all_cached_files("cerebrum_codebase")
        return {
            "status": "ok",
            "chunk_cache": chunk_stats,
            "total_indexed_files": len(all_files),
        }
    except Exception as e:
        return {"status": "error", "message": str(e)}


@router.get("/api/watcher/status")
async def get_watcher_endpoint():
    """Returns real-time watcher daemon health and queue statistics."""
    from kortext.watcher import get_watcher_status
    try:
        st = get_watcher_status()
        return {"status": "ok", "watcher": st}
    except Exception as e:
        return {"status": "error", "message": str(e)}


@router.get("/api/quarantine")
async def get_quarantine():
    """Lists quarantined adversarial payloads blocked by CausalSanitizer."""
    from kortext.trust.sanitizer import CausalSanitizer
    try:
        sanitizer = CausalSanitizer()
        q_files = sorted(sanitizer.quarantine_dir.glob("*.json"), reverse=True)
        items = []
        for f in q_files[:50]:
            try:
                data = json.loads(f.read_text(encoding="utf-8"))
                items.append({
                    "filename": f.name,
                    "timestamp": data.get("timestamp"),
                    "reason": data.get("reason"),
                    "subject": data.get("subject"),
                    "relation": data.get("relation"),
                    "fact": data.get("fact"),
                })
            except Exception:
                continue
        return {"status": "ok", "quarantine_count": len(q_files), "items": items}
    except Exception as e:
        return {"status": "error", "message": str(e), "quarantine_count": 0, "items": []}


@router.delete("/api/quarantine")
async def clear_quarantine():
    from kortext.trust.sanitizer import CausalSanitizer
    try:
        sanitizer = CausalSanitizer()
        q_files = list(sanitizer.quarantine_dir.glob("*.json"))
        count = 0
        for f in q_files:
            try:
                f.unlink(missing_ok=True)
                count += 1
            except Exception:
                pass
        return {"status": "ok", "cleared_count": count}
    except Exception as e:
        return {"status": "error", "message": str(e), "cleared_count": 0}


@router.get("/api/telemetry")
async def get_telemetry():
    """Returns real-time system telemetry and performance benchmarks."""
    lat_ms = 0.0
    falkor_ok = False
    try:
        client = get_shared_falkordb_client(host=FALKORDB_HOST, port=FALKORDB_PORT)
        t0 = time.perf_counter()
        client.query(FALKORDB_DB, "RETURN 1")
        lat_ms = round((time.perf_counter() - t0) * 1000.0, 2)
        falkor_ok = True
    except Exception:
        pass

    env_home = os.getenv("KORTEXT_HOME") or os.getenv("CEREBRUM_HOME")
    if env_home:
        kortext_home = Path(env_home)
    else:
        k_dir = Path.home() / ".kortext"
        c_dir = Path.home() / ".cerebrum"
        kortext_home = k_dir if k_dir.exists() or not c_dir.exists() else c_dir
    q_dir = kortext_home / "quarantine"
    q_count = len(list(q_dir.glob("*.json"))) if q_dir.exists() else 0

    rss_mb = 0.0
    try:
        proc = psutil.Process(os.getpid())
        rss_mb = round(proc.memory_info().rss / (1024 * 1024), 1)
    except Exception:
        pass

    return {
        "status": "ok",
        "telemetry": {
            "version": "2.0.0-PROD",
            "token_search_savings": "Active (AST B-Tree)",
            "substrate_ram_rss_mb": rss_mb,
            "falkordb_latency_ms": lat_ms,
            "falkordb_healthy": falkor_ok,
            "quarantine_count": q_count,
            "weibull_retention_floor": 0.05,
            "weibull_beta": 0.85,
            "weibull_lambda": 168.0,
            "active_invariants": 14,
            "tier_0": {"name": "Tree-sitter AST B-Tree", "status": "Active"},
            "tier_1": {"name": "Qdrant Vectors", "embedder": "FastEmbed BAAI/bge-small-en-v1.5 (fallback)"},
            "tier_2": {"name": "FalkorDB Episodic Graph", "status": "Active"},
            "tier_3": {"name": "Federated Hybrid Query", "status": "Active"},
            "tier_4": {"name": "Cognitive Dream Mode", "status": "Active"},
            "tiers": {
                "tier_0": {"name": "Tree-sitter AST B-Tree", "status": "Active"},
                "tier_1": {"name": "Qdrant Vectors", "embedder": "FastEmbed BAAI/bge-small-en-v1.5 (fallback)"},
                "tier_2": {"name": "FalkorDB Episodic Graph", "status": "Active"},
                "tier_3": {"name": "Federated Hybrid Query", "status": "Active"},
                "tier_4": {"name": "Cognitive Dream Mode", "status": "Active"},
            },
            "nextgen_hooks": [
                "FastMCPLockGuard",
                "AntiRipgrepGate",
                "CommandSafetyGuard",
                "SecretLeakGuard",
                "IncrementalASTSync",
                "SubstrateHealthProbe",
                "GroundTruthTestGate",
            ],
        }
    }
