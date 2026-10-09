"""
Centralized Environment Variable Resolver for Kortext.

Provides deterministic resolution with Kortext -> Cerebrum -> Raw fallback ordering,
type-safe parsing, and specialized getters for substrate services.
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Optional

from kortext._home import get_kortext_home

__all__ = [
    "get_env",
    "get_int_env",
    "get_float_env",
    "get_bool_env",
    "get_falkordb_socket",
    "get_falkordb_host",
    "get_falkordb_port",
    "get_falkordb_database",
    "get_falkordb_symbols_graph",
    "get_qdrant_url",
    "get_qdrant_collection",
    "get_embed_base_url",
    "get_embed_model_name",
    "get_rerank_base_url",
]


def get_env(name: str, default: Optional[str] = None) -> Optional[str]:
    """
    Resolve environment variable with Kortext -> Cerebrum -> Raw fallback.

    Resolution order:
    a) If `name` already starts with 'KORTEXT_' or 'CEREBRUM_', check directly.
       If empty or unset, fall back to CEREBRUM_ equivalent if name started with KORTEXT_.
    b) Otherwise, check `KORTEXT_{name}` first.
    c) If not found or empty, fall back to `CEREBRUM_{name}`.
    d) If not found or empty, fall back to `{name}`.
    e) Return `default` if none found.
    """
    if name.startswith(("KORTEXT_", "CEREBRUM_")):
        val = os.getenv(name)
        if val is not None and val != "":
            return val
        if name.startswith("KORTEXT_"):
            cerebrum_key = "CEREBRUM_" + name[len("KORTEXT_"):]
            val = os.getenv(cerebrum_key)
            if val is not None and val != "":
                return val
        return default

    kortext_val = os.getenv(f"KORTEXT_{name}")
    if kortext_val is not None and kortext_val != "":
        return kortext_val

    cerebrum_val = os.getenv(f"CEREBRUM_{name}")
    if cerebrum_val is not None and cerebrum_val != "":
        return cerebrum_val

    raw_val = os.getenv(name)
    if raw_val is not None and raw_val != "":
        return raw_val

    return default


def get_int_env(name: str, default: int) -> int:
    """Resolve an integer environment variable with fallback to default."""
    val = get_env(name)
    if val is None:
        return default
    try:
        return int(val.strip())
    except (ValueError, TypeError):
        return default


def get_float_env(name: str, default: float) -> float:
    """Resolve a float environment variable with fallback to default."""
    val = get_env(name)
    if val is None:
        return default
    try:
        return float(val.strip())
    except (ValueError, TypeError):
        return default


def get_bool_env(name: str, default: bool) -> bool:
    """
    Resolve a boolean environment variable (case-insensitive true/false, 1/0, yes/no).
    Returns default if missing or unrecognized.
    """
    val = get_env(name)
    if val is None:
        return default
    cleaned = val.strip().lower()
    if cleaned in ("1", "true", "yes", "t", "y", "on"):
        return True
    if cleaned in ("0", "false", "no", "f", "n", "off"):
        return False
    return default


def get_falkordb_socket() -> Optional[Path]:
    """
    Resolve FalkorDB Unix domain socket path.
    Uses get_kortext_home() / 'run' / 'falkordb.sock' as default.
    """
    val = get_env("FALKORDB_SOCKET")
    if val:
        cleaned = val.strip()
        if cleaned.lower() in ("none", "disabled", "false", "0"):
            return None
        return Path(os.path.expanduser(cleaned))

    default_sock = get_kortext_home() / "run" / "falkordb.sock"
    if not (os.getenv("KORTEXT_HOME") or os.getenv("CEREBRUM_HOME")) and not default_sock.exists():
        legacy_sock = Path.home() / ".cerebrum" / "run" / "falkordb.sock"
        if legacy_sock.exists():
            return legacy_sock
    return default_sock


def get_falkordb_host() -> str:
    """Resolve FalkorDB host address (default '127.0.0.1')."""
    return get_env("FALKORDB_HOST", "127.0.0.1") or "127.0.0.1"


def get_falkordb_port() -> int:
    """Resolve FalkorDB TCP port (default 6379)."""
    return get_int_env("FALKORDB_PORT", 6379)


def get_falkordb_database() -> str:
    """Resolve FalkorDB database name (default 'kortext', falls back to 'cerebrum')."""
    val = get_env("FALKORDB_DATABASE") or get_env("DATABASE")
    if val:
        return val
    if os.getenv("CEREBRUM_HOME") and not os.getenv("KORTEXT_HOME"):
        return "cerebrum"
    return "kortext"


def get_falkordb_symbols_graph() -> str:
    """Resolve FalkorDB symbols graph name (default 'kortext_symbols', falls back to 'cerebrum_symbols')."""
    val = (
        get_env("FALKORDB_SYMBOLS_GRAPH")
        or get_env("SYMBOLS_GRAPH")
        or get_env("SYMBOLS_GRAPH_NAME")
    )
    if val:
        return val
    if os.getenv("CEREBRUM_HOME") and not os.getenv("KORTEXT_HOME"):
        return "cerebrum_symbols"
    return "kortext_symbols"


def get_qdrant_url() -> str:
    """Resolve Qdrant HTTP URL (default 'http://localhost:6333')."""
    return get_env("QDRANT_URL", "http://localhost:6333") or "http://localhost:6333"


def get_qdrant_collection() -> str:
    """Resolve Qdrant collection name (default 'kortext_codebase', falls back to 'cerebrum_codebase')."""
    val = (
        get_env("QDRANT_COLLECTION")
        or get_env("COLLECTION")
        or get_env("COLLECTION_NAME")
    )
    if val:
        return val
    if os.getenv("CEREBRUM_HOME") and not os.getenv("KORTEXT_HOME"):
        return "cerebrum_codebase"
    return "kortext_codebase"


def get_embed_base_url() -> str:
    """Resolve embedding server base URL (default 'http://localhost:8000/v1')."""
    return get_env("EMBED_BASE_URL", "http://localhost:8000/v1") or "http://localhost:8000/v1"


def get_embed_model_name() -> str:
    """Resolve embedding model name (default 'mlx-community--Qwen3-Embedding-8B-4bit-DWQ')."""
    return (
        get_env("EMBED_MODEL_NAME", "mlx-community--Qwen3-Embedding-8B-4bit-DWQ")
        or "mlx-community--Qwen3-Embedding-8B-4bit-DWQ"
    )


def get_rerank_base_url() -> str:
    """Resolve cross-encoder reranker base URL (default 'http://localhost:8000/v1')."""
    return get_env("RERANK_BASE_URL", "http://localhost:8000/v1") or "http://localhost:8000/v1"
