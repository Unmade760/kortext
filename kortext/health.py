"""
Substrate health verification and observability engine for Kortext.

Consolidates health checks across:
- Qdrant Vector Store (Remote healthz vs Embedded Zero-Docker metadata discovery)
- FalkorDB Graph Engine (Unix Domain Socket IPC first, with TCP :6379 fallback)
- Inference server (oMLX embedding / chat endpoint)
- Dashboard UI (:8004/api/cache/stats)
- FalkorDB Browser UI (:3000)
- Architectural invariant drift audit (AST body grounding)

Adheres to Invariant 3: Substrate Resilience. Secondary processes and status
monitors NEVER instantiate QdrantClient(path=...) directly.
"""

from __future__ import annotations

import asyncio
from datetime import datetime
import json
import logging
import os
from pathlib import Path
import socket
from typing import Any, Dict, List, Optional
import warnings

import httpx

from kortext._home import KORTEXT_HOME, get_kortext_home
from kortext.falkordb_client import get_shared_falkordb_client
from kortext.retrieval.discovery import discover_vector_collections

logger = logging.getLogger(__name__)


def _probe_falkordb_sync() -> Dict[str, Any]:
    """
    Probe FalkorDB using get_shared_falkordb_client() wrapped in asyncio.to_thread.
    Prefers Unix domain socket IPC with TCP :6379 fallback.
    """
    kortext_home = get_kortext_home()
    falkor_sock = kortext_home / "run" / "falkordb.sock"
    if not (os.getenv("KORTEXT_HOME") or os.getenv("CEREBRUM_HOME")) and not falkor_sock.exists():
        legacy_sock = Path.home() / ".cerebrum" / "run" / "falkordb.sock"
        if legacy_sock.exists():
            falkor_sock = legacy_sock
    falkor_host = os.getenv("FALKORDB_HOST", "127.0.0.1")
    falkor_port = int(os.getenv("FALKORDB_PORT", "6379"))

    # 1. Direct UDS ping check
    if falkor_sock.is_socket():
        try:
            import redis
            r = redis.Redis(unix_socket_path=str(falkor_sock), socket_timeout=2.0)
            if r.ping():
                return {
                    "healthy": True,
                    "status_display": "✅ RUNNING (Unix Socket)",
                    "service_status": "RUNNING",
                    "port": "Unix Socket",
                    "error": None,
                }
        except Exception as e:
            logger.debug("Direct FalkorDB UDS ping failed: %s", e)

    # 2. Probe via singleton FalkorDBClient
    try:
        client = get_shared_falkordb_client(host=falkor_host, port=falkor_port)
        r = client.get_redis()
        if r.ping():
            is_socket = bool(r.connection_pool.connection_kwargs.get("path")) or falkor_sock.is_socket()
            conn_type = "Unix Socket" if is_socket else f"TCP :{falkor_port}"
            port_val = "Unix Socket" if is_socket else falkor_port
            return {
                "healthy": True,
                "status_display": f"✅ RUNNING ({conn_type})",
                "service_status": "RUNNING",
                "port": port_val,
                "error": None,
            }
    except Exception as e:
        logger.debug("FalkorDBClient get_redis ping failed: %s", e)

    # 3. Fallback to TCP loopback socket probe
    try:
        with socket.create_connection((falkor_host, falkor_port), timeout=2.0):
            return {
                "healthy": True,
                "status_display": f"✅ RUNNING (TCP :{falkor_port})",
                "service_status": "RUNNING",
                "port": falkor_port,
                "error": None,
            }
    except Exception as e:
        return {
            "healthy": False,
            "status_display": f"❌ DOWN ({e})",
            "service_status": "DOWN",
            "port": "Unix Socket" if falkor_sock.is_socket() else falkor_port,
            "error": str(e),
        }


async def _probe_qdrant(client: httpx.AsyncClient) -> Dict[str, Any]:
    """Probe Qdrant vector store (remote HTTP or zero-docker embedded metadata discovery)."""
    qdrant_url = os.getenv("QDRANT_URL")
    if qdrant_url:
        target_url = qdrant_url.rstrip("/")
        status_code = None
        error_name = None
        is_ok = False
        try:
            resp = await client.get(f"{target_url}/healthz", timeout=3.0)
            status_code = resp.status_code
            is_ok = resp.status_code < 500
        except Exception as e:
            error_name = type(e).__name__
            try:
                resp = await client.get(f"{target_url}/collections", timeout=3.0)
                status_code = resp.status_code
                is_ok = resp.status_code < 400
            except Exception as e2:
                error_name = type(e2).__name__

        healthy = is_ok and (status_code is not None and status_code < 400)
        if is_ok:
            status_display = "✅ RUNNING" if (status_code and status_code < 500) else f"⚠️  HTTP {status_code}"
            service_status = "RUNNING"
        else:
            status_display = f"❌ DOWN ({error_name or f'HTTP {status_code}'})"
            service_status = "DOWN"

        return {
            "healthy": healthy,
            "status_display": status_display,
            "service_status": service_status,
            "port": 6333,
            "url": f"{target_url}/dashboard",
            "description": "Remote Qdrant vector store",
        }
    else:
        kortext_home = get_kortext_home()
        qpath = kortext_home / "qdrant"
        if not (os.getenv("KORTEXT_HOME") or os.getenv("CEREBRUM_HOME")) and not qpath.exists() and (Path.home() / ".cerebrum" / "qdrant").exists():
            qpath = Path.home() / ".cerebrum" / "qdrant"
        meta_file = qpath / "meta.json"

        try:
            collections = await asyncio.to_thread(discover_vector_collections)
            col_names = [c["name"] for c in collections if isinstance(c, dict) and "name" in c]
            if col_names or meta_file.is_file():
                col_text = f" ({len(col_names)} collections: {', '.join(col_names)})" if col_names else ""
                desc = (
                    f"In-process Rust engine ({len(col_names)} collections: {', '.join(col_names)})"
                    if col_names
                    else "In-process Rust engine (Zero-Docker)"
                )
                return {
                    "healthy": True,
                    "status_display": f"✅ EMBEDDED{col_text}",
                    "service_status": "EMBEDDED",
                    "port": "Embedded",
                    "url": "#collections",
                    "description": desc,
                }
            elif qpath.is_dir():
                return {
                    "healthy": True,
                    "status_display": "✅ EMBEDDED (directory active)",
                    "service_status": "EMBEDDED",
                    "port": "Embedded",
                    "url": "#collections",
                    "description": "In-process Rust engine (Zero-Docker)",
                }
            else:
                return {
                    "healthy": False,
                    "status_display": "❌ DOWN (Storage path missing)",
                    "service_status": "DOWN",
                    "port": "Embedded",
                    "url": "#collections",
                    "description": f"Storage directory {qpath} not found",
                }
        except Exception as e:
            if qpath.is_dir():
                return {
                    "healthy": True,
                    "status_display": f"⚠️ EMBEDDED (meta read error: {e})",
                    "service_status": "EMBEDDED",
                    "port": "Embedded",
                    "url": "#collections",
                    "description": f"In-process Rust engine (meta read error: {e})",
                }
            else:
                return {
                    "healthy": False,
                    "status_display": f"❌ DOWN ({type(e).__name__})",
                    "service_status": "DOWN",
                    "port": "Embedded",
                    "url": "#collections",
                    "description": f"Storage directory {qpath} missing or unreadable",
                }


async def _probe_inference(client: httpx.AsyncClient) -> Dict[str, Any]:
    """Probe inference server health."""
    embed_url = os.getenv("EMBED_BASE_URL", "http://127.0.0.1:8000/v1")
    base_host = embed_url.replace("/v1", "").rstrip("/")
    inference_health = os.getenv(
        "INFERENCE_HEALTH_URL",
        f"{base_host}/health" if ("localhost" in base_host or "127.0.0.1" in base_host) else embed_url,
    )
    inference_health = inference_health.replace("://localhost", "://127.0.0.1")

    omlx_data = None
    try:
        resp = await client.get(inference_health, timeout=2.0)
        inf_ok = resp.status_code < 500
        inf_healthy = resp.status_code < 400
        status_display = "✅ RUNNING" if inf_ok else f"⚠️  HTTP {resp.status_code}"
        service_status = "RUNNING" if inf_ok else "DOWN"
        try:
            omlx_data = resp.json()
        except Exception:
            omlx_data = None
        return {
            "healthy": inf_healthy,
            "status_display": status_display,
            "service_status": service_status,
            "port": 8000,
            "url": base_host,
            "description": "Inference & embedding endpoint",
            "meta": omlx_data,
        }
    except Exception as e:
        return {
            "healthy": False,
            "status_display": f"❌ DOWN ({type(e).__name__})",
            "service_status": "DOWN",
            "port": 8000,
            "url": base_host,
            "description": "Inference & embedding endpoint",
            "meta": None,
        }


async def _probe_dashboard(client: httpx.AsyncClient) -> Dict[str, Any]:
    """Probe Dashboard UI health."""
    dash_host = os.getenv("DASHBOARD_HOST", "127.0.0.1")
    dash_port_str = os.getenv("DASHBOARD_PORT", "8004")
    dash_port = int(dash_port_str) if dash_port_str.isdigit() else 8004
    dash_url = f"http://{dash_host}:{dash_port}/api/cache/stats"

    try:
        resp = await client.get(dash_url, timeout=2.0)
        dash_ok = resp.status_code < 500
        dash_healthy = resp.status_code < 400
        status_display = "✅ RUNNING" if dash_ok else f"⚠️  HTTP {resp.status_code}"
        service_status = "RUNNING" if dash_ok else "DOWN"
        return {
            "healthy": dash_healthy,
            "status_display": status_display,
            "service_status": service_status,
            "port": dash_port,
            "url": f"http://{dash_host}:{dash_port}",
            "description": "FastAPI telemetry and graph observability dashboard",
        }
    except Exception as e:
        return {
            "healthy": False,
            "status_display": f"❌ DOWN ({type(e).__name__})",
            "service_status": "DOWN",
            "port": dash_port,
            "url": f"http://{dash_host}:{dash_port}",
            "description": "FastAPI telemetry and graph observability dashboard",
        }


async def _probe_browser_ui(client: httpx.AsyncClient) -> Dict[str, Any]:
    """Probe FalkorDB Browser UI (:3000)."""
    try:
        resp = await client.get("http://127.0.0.1:3000", timeout=2.0)
        browser_ok = resp.status_code < 400
        return {
            "name": "FalkorDB Browser UI",
            "port": 3000,
            "url": "http://127.0.0.1:3000",
            "status": "RUNNING" if browser_ok else "OFFLINE",
            "healthy": browser_ok,
            "description": "Official Cypher query visualizer & browser (optional)",
        }
    except Exception:
        return {
            "name": "FalkorDB Browser UI",
            "port": 3000,
            "url": "http://127.0.0.1:3000",
            "status": "OFFLINE",
            "healthy": False,
            "description": "Official Cypher query visualizer & browser (optional)",
        }


def _check_invariants_sync() -> tuple[Optional[Dict[str, Any]], Optional[Exception]]:
    """Audit architectural invariant drift via InvariantGroundingEngine."""
    try:
        from kortext.invariants import InvariantGroundingEngine
        inv_eng = InvariantGroundingEngine()
        return inv_eng.audit_invariant_drift(), None
    except Exception as e:
        return None, e


async def audit_kortext_health(
    include_browser_ui: bool = False,
    include_invariants: bool = True,
) -> Dict[str, Any]:
    """
    Consolidated health audit across all Kortext substrate services.

    Compatible with both FastMCP tool (top-level service string keys) and
    FastAPI status endpoint ('services' list and 'timestamp').

    Args:
        include_browser_ui: When True, probes FalkorDB Browser on :3000.
        include_invariants: When True, runs AST grounding invariant drift audit.

    Returns:
        Structured health report dictionary.
    """
    async with httpx.AsyncClient(timeout=3.0) as client:
        # Launch concurrent probes
        probe_coros: List[Any] = [
            _probe_qdrant(client),
            _probe_inference(client),
            _probe_dashboard(client),
            asyncio.to_thread(_probe_falkordb_sync),
        ]

        if include_browser_ui:
            probe_coros.append(_probe_browser_ui(client))

        if include_invariants:
            probe_coros.append(asyncio.to_thread(_check_invariants_sync))

        results = await asyncio.gather(*probe_coros)

    qdrant_res: Dict[str, Any] = results[0]
    inf_res: Dict[str, Any] = results[1]
    dash_res: Dict[str, Any] = results[2]
    falkor_res: Dict[str, Any] = results[3]

    idx = 4
    browser_res: Optional[Dict[str, Any]] = None
    if include_browser_ui:
        browser_res = results[idx]
        idx += 1

    drift_res: Optional[Dict[str, Any]] = None
    drift_err: Optional[Exception] = None
    if include_invariants:
        drift_res, drift_err = results[idx]
        idx += 1

    report: Dict[str, Any] = {
        "qdrant": qdrant_res["status_display"],
        "falkordb": falkor_res["status_display"],
        "inference_server": inf_res["status_display"],
        "kortext_dashboard": dash_res["status_display"],
        "cerebrum_dashboard": dash_res["status_display"],
    }

    if include_invariants:
        if drift_err:
            report["invariants"] = f"⚠️ Check skipped ({type(drift_err).__name__}: {drift_err})"
        elif drift_res is not None:
            v_cnt = drift_res.get("verified_count", 0)
            d_cnt = drift_res.get("drifted_count", 0)
            o_cnt = drift_res.get("orphaned_count", 0)
            t_cnt = drift_res.get("total_grounded", 0)
            report["invariants"] = (
                f"✅ {v_cnt} verified, {d_cnt} drifted, {o_cnt} orphaned (total: {t_cnt})"
            )
            if d_cnt > 0:
                report["recommendation"] = (
                    f"⚠️ {d_cnt} architectural invariant(s) drifted from live AST bodies. "
                    f"Run trigger_dream_mode() to review and consolidate."
                )

    # Compile structured services list for dashboard / UI consumers
    services: List[Dict[str, Any]] = [
        {
            "name": "Qdrant Vector Store",
            "port": qdrant_res["port"],
            "url": qdrant_res["url"],
            "status": qdrant_res["service_status"],
            "healthy": qdrant_res["healthy"],
            "description": qdrant_res["description"],
        },
        {
            "name": "FalkorDB Graph Engine",
            "port": falkor_res["port"],
            "url": "http://127.0.0.1:3000",
            "status": falkor_res["service_status"],
            "healthy": falkor_res["healthy"],
            "description": "GraphBLAS native temporal property graph (Unix Socket / :6379)",
        },
    ]

    if include_browser_ui and browser_res is not None:
        services.append(browser_res)

    inf_entry: Dict[str, Any] = {
        "name": "oMLX Admin Dashboard",
        "port": inf_res["port"],
        "url": inf_res["url"],
        "status": inf_res["service_status"],
        "healthy": inf_res["healthy"],
        "description": inf_res["description"],
    }
    if inf_res.get("meta") is not None:
        inf_entry["meta"] = inf_res["meta"]
    services.append(inf_entry)

    services.append({
        "name": "Kortext Dashboard",
        "port": dash_res["port"],
        "url": dash_res["url"],
        "status": dash_res["service_status"],
        "healthy": dash_res["healthy"],
        "description": dash_res["description"],
    })

    report["services"] = services
    report["timestamp"] = datetime.now().isoformat()

    # Overall recommendation
    if any(
        "❌ DOWN" in str(v)
        for k, v in report.items()
        if k not in ("services", "timestamp") and isinstance(v, str)
    ):
        down_msg = "⚠️  One or more Kortext services are down. Run 'kortext start' to bring them online."
        if "recommendation" in report:
            report["recommendation"] = f"{down_msg} {report['recommendation']}"
        else:
            report["recommendation"] = down_msg
    elif "recommendation" not in report:
        report["recommendation"] = "✅ All core Kortext services are operational."

    return report


async def audit_cerebrum_health(
    include_browser_ui: bool = False,
    include_invariants: bool = True,
    *args: Any,
    **kwargs: Any,
) -> Dict[str, Any]:
    """Deprecated alias for audit_kortext_health."""
    warnings.warn(
        "audit_cerebrum_health is deprecated, use audit_kortext_health instead.",
        DeprecationWarning,
        stacklevel=2,
    )
    return await audit_kortext_health(
        include_browser_ui=include_browser_ui,
        include_invariants=include_invariants,
        *args,
        **kwargs,
    )

