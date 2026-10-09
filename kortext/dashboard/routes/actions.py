"""
Action triggers: dream consolidation, collection creation, cache clearing,
SCIP/symbol indexing, and Task DAG management.
"""

import asyncio
import json
import os
import shutil
import subprocess
from pathlib import Path
from typing import Any, Dict, List, Optional

import httpx
from fastapi import APIRouter, Request

router = APIRouter(tags=["actions"])

from kortext._home import get_kortext_home

KORTEXT_ROOT = Path(__file__).resolve().parents[3]
CEREBRUM_ROOT = KORTEXT_ROOT


@router.post("/api/dream")
async def trigger_dream(request: Request):
    """Triggers on-demand Kortext Dream Mode consolidation cycle."""
    try:
        body = await request.json()
    except Exception:
        body = {}
    project = body.get("project", "kortext")
    purge_stale = bool(body.get("purge_stale", False))

    from kortext.dream import KortextDreamEngine
    engine = KortextDreamEngine()
    try:
        report = await engine.dream(project=project, purge_stale=purge_stale)
        return {"status": "ok", "report": report}
    except Exception as e:
        return {"status": "error", "message": str(e)}


def _is_sole_custodian_running() -> bool:
    """Checks if the primary kortext.server daemon is currently running."""
    try:
        import psutil

        current_pid = os.getpid()
        for proc in psutil.process_iter(["pid", "name", "cmdline"]):
            try:
                if proc.info["pid"] == current_pid:
                    continue
                cmdline = " ".join(proc.info.get("cmdline") or [])
                if any(srv in cmdline for srv in ("kortext.server", "kortext-server", "cerebrum.server", "cerebrum-server")):
                    return True
            except (psutil.NoSuchProcess, psutil.AccessDenied):
                continue
    except Exception:
        pass
    return False


async def _check_remote_qdrant(url: str = "http://127.0.0.1:6333") -> bool:
    """Checks if a remote/local Qdrant HTTP service is reachable."""
    try:
        async with httpx.AsyncClient(timeout=1.0) as client:
            resp = await client.get(f"{url.rstrip('/')}/collections")
            return resp.status_code == 200
    except Exception:
        return False


def _get_default_collection_schema(embed_dim: int = 4096) -> Dict[str, Any]:
    """Generates the embedded Qdrant schema matching QdrantClient create_collection format."""
    return {
        "vectors": {
            "text-dense": {
                "size": embed_dim,
                "distance": "Cosine",
                "hnsw_config": None,
                "quantization_config": None,
                "on_disk": True,
                "memory": None,
                "datatype": None,
                "multivector_config": None,
            }
        },
        "shard_number": None,
        "sharding_method": None,
        "replication_factor": None,
        "write_consistency_factor": None,
        "on_disk_payload": None,
        "payload": None,
        "hnsw_config": None,
        "wal_config": None,
        "optimizers_config": None,
        "quantization_config": None,
        "sparse_vectors": {
            "text-sparse-new": {
                "index": {
                    "full_scan_threshold": None,
                    "on_disk": True,
                    "memory": None,
                    "datatype": None,
                },
                "modifier": None,
            }
        },
        "strict_mode_config": None,
        "metadata": None,
    }


@router.post("/api/collections")
async def create_collection(request: Request):
    """Creates a new Qdrant collection configured for Qwen3-Embedding (4096-dim, Cosine)."""
    try:
        body = await request.json()
        name = body.get("name", "").strip()
        if not name:
            return {"status": "error", "message": "Collection name is required"}

        # 1. If explicit QDRANT_URL is set, provision via remote HTTP endpoint
        qdrant_url = os.getenv("QDRANT_URL")
        if qdrant_url:
            async with httpx.AsyncClient(timeout=5.0) as client:
                payload = {
                    "vectors": {
                        "size": 4096,
                        "distance": "Cosine",
                    }
                }
                resp = await client.put(f"{qdrant_url.rstrip('/')}/collections/{name}", json=payload)
                if resp.status_code in [200, 201]:
                    return {"status": "ok", "message": f"Collection '{name}' created successfully."}
                else:
                    return {"status": "error", "message": resp.text}

        # 2. Zero-Docker mode (when QDRANT_URL is unset)
        # Invariant 3 Mandate: Do NOT instantiate QdrantClient(path=...) in secondary dashboard process
        # if the store is open or sole custodian daemon is running.
        kortext_home = get_kortext_home()
        qpath = kortext_home / "qdrant"
        meta_file = qpath / "meta.json"
        custodian_running = _is_sole_custodian_running()

        if meta_file.is_file() or custodian_running:
            try:
                qpath.mkdir(parents=True, exist_ok=True)
                if meta_file.is_file():
                    try:
                        meta_data = json.loads(meta_file.read_text(encoding="utf-8"))
                    except Exception:
                        meta_data = {"collections": {}, "aliases": {}}
                else:
                    meta_data = {"collections": {}, "aliases": {}}

                collections = meta_data.setdefault("collections", {})
                if name not in collections:
                    collections[name] = _get_default_collection_schema(embed_dim=4096)
                    col_dir = qpath / "collection" / name
                    col_dir.mkdir(parents=True, exist_ok=True)

                    # Atomic write to meta.json
                    tmp_file = meta_file.with_suffix(f".tmp.{os.getpid()}")
                    tmp_file.write_text(json.dumps(meta_data, indent=2), encoding="utf-8")
                    tmp_file.replace(meta_file)

                return {"status": "ok", "message": f"Collection '{name}' created successfully in native embedded Qdrant."}
            except Exception as e:
                return {"status": "error", "message": f"Failed to safely update meta.json: {e}"}

        # 3. Check if remote URL (e.g. local 127.0.0.1:6333) is available before direct fallback
        if await _check_remote_qdrant("http://127.0.0.1:6333"):
            try:
                async with httpx.AsyncClient(timeout=5.0) as client:
                    payload = {
                        "vectors": {
                            "size": 4096,
                            "distance": "Cosine",
                        }
                    }
                    resp = await client.put(f"http://127.0.0.1:6333/collections/{name}", json=payload)
                    if resp.status_code in [200, 201]:
                        return {"status": "ok", "message": f"Collection '{name}' created successfully."}
                    else:
                        return {"status": "error", "message": resp.text}
            except Exception as e:
                return {"status": "error", "message": f"Failed to provision collection via local Qdrant: {e}"}

        # 4. Fallback to EmbeddedQdrantEngine guarded with exception handling (no daemon is holding lock)
        try:
            from kortext.retrieval.qdrant_engine import EmbeddedQdrantEngine

            engine = EmbeddedQdrantEngine()
            engine.ensure_collection(name, embed_dim=4096)
            return {"status": "ok", "message": f"Collection '{name}' created successfully in native embedded Qdrant."}
        except Exception as e:
            err_msg = str(e)
            if "lock" in err_msg.lower() or "operationalerror" in err_msg.lower() or "resource temporarily unavailable" in err_msg.lower():
                return {
                    "status": "error",
                    "message": f"Embedded Qdrant store is locked by sole custodian daemon ({err_msg}). Provisioning aborted to preserve Invariant 3.",
                }
            return {"status": "error", "message": f"Embedded Qdrant provisioning failed: {err_msg}"}
    except Exception as e:
        return {"status": "error", "message": str(e)}


@router.post("/api/cache/clear")
async def clear_cache():
    """Clears the chunk embedding SQLite cache."""
    from kortext.cache import ChunkEmbeddingCache
    try:
        chunk_cache = ChunkEmbeddingCache()
        purged_count = await asyncio.to_thread(chunk_cache.clear)
        return {"status": "ok", "purged_chunks": purged_count}
    except Exception as e:
        return {"status": "error", "message": str(e)}


@router.post("/api/scip/auto")
@router.post("/api/symbols/index")
async def run_scip_auto():
    """Triggers automated SCIP indexing and ingestion."""
    scip_path = KORTEXT_ROOT / "index.scip"
    scip_py = shutil.which("scip-python")
    if scip_path.exists():
        from kortext.symbols.scip import SCIPImporter
        importer = SCIPImporter()
        stats = await asyncio.to_thread(importer.ingest_scip_file, str(scip_path))
        return {"status": "ok", "message": "Ingested existing index.scip", "stats": stats}
    elif scip_py:
        try:
            cmd = [scip_py, "index", "--project-root", str(KORTEXT_ROOT), "--output", str(scip_path)]
            p = await asyncio.to_thread(subprocess.run, cmd, capture_output=True, text=True, timeout=60)
            if p.returncode == 0 and scip_path.exists():
                from kortext.symbols.scip import SCIPImporter
                importer = SCIPImporter()
                stats = await asyncio.to_thread(importer.ingest_scip_file, str(scip_path))
                return {"status": "ok", "message": "Generated and ingested index.scip", "stats": stats}
            return {"status": "error", "message": f"scip-python failed: {p.stderr}"}
        except Exception as e:
            return {"status": "error", "message": str(e)}
    else:
        return {
            "status": "not_installed",
            "message": "Neither index.scip nor scip-python CLI tool was found. Run `npm install -g @sourcegraph/scip-python` or generate index.scip.",
        }


@router.get("/api/tasks")
async def get_tasks(include_graph: bool = True):
    """Returns Task DAG tasks and dependency graph formatted for Vis.js."""
    from kortext.tasks.tracker import TaskDAGTracker
    try:
        tracker = TaskDAGTracker()
        data = tracker.get_graph_data() if include_graph else {"tasks": tracker.get_all_tasks(), "nodes": [], "edges": []}
        ready = tracker.get_ready_tasks()
        return {
            "status": "ok",
            "tasks": data.get("tasks", []),
            "nodes": data.get("nodes", []),
            "edges": data.get("edges", []),
            "ready_tasks": ready,
        }
    except Exception as e:
        return {"status": "error", "message": str(e), "tasks": [], "nodes": [], "edges": [], "ready_tasks": []}


@router.post("/api/tasks")
async def manage_task_endpoint(request: Request):
    """Creates a new Task or updates existing task state in FalkorDB."""
    from kortext.tasks.tracker import TaskDAGTracker
    try:
        body = await request.json()
        action = body.get("action", "create")
        tracker = TaskDAGTracker()
        if action == "create":
            title = body.get("title")
            if not title:
                return {"status": "error", "message": "Task title is required"}
            tid = tracker.create_task(
                title=title,
                description=body.get("description", ""),
                complexity=int(body.get("complexity", 1)),
                assigned_to=body.get("assigned_to", "primary"),
                depends_on=body.get("depends_on"),
            )
            return {"status": "ok", "task_id": tid}
        elif action == "update_status":
            tid = body.get("task_id")
            st = body.get("status")
            if not tid or not st:
                return {"status": "error", "message": "task_id and status are required"}
            err = body.get("error")
            tracker.update_task_status(tid, status=st, error=err)
            return {"status": "ok", "task_id": tid, "updated_status": st}
        return {"status": "error", "message": f"Unknown action: {action}"}
    except Exception as e:
        return {"status": "error", "message": str(e)}
