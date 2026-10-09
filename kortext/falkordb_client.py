"""
Canonical FalkorDB Client & Token-Safe Cypher Query Engine for Kortext.

Provides:
1. Resilient Redis connection lifecycle and reconnect logic.
2. Token-safe Cypher parameter interpolation using word boundaries
   and length-descending key sorting (eliminating prefix collision vulnerabilities).
3. Schema index verification for Symbol, File, Document, Tag, and Concept nodes.
"""
from __future__ import annotations

import logging
import os
from pathlib import Path
import re
from typing import Any, Dict, List, Optional, Set, Tuple
from falkordb.helpers import stringify_param_value
import redis

logger = logging.getLogger(__name__)


from kortext._home import KORTEXT_HOME, get_kortext_home


def get_default_socket() -> Path:
    sock = get_kortext_home() / "run" / "falkordb.sock"
    if not (os.getenv("KORTEXT_HOME") or os.getenv("CEREBRUM_HOME")) and not sock.exists():
        legacy_sock = Path.home() / ".cerebrum" / "run" / "falkordb.sock"
        if legacy_sock.exists():
            return legacy_sock
    return sock


CEREBRUM_HOME = KORTEXT_HOME
DEFAULT_SOCKET = get_default_socket()

FALKORDB_HOST = os.getenv("FALKORDB_HOST", "127.0.0.1")
FALKORDB_PORT = int(os.getenv("FALKORDB_PORT", "6379"))
FALKORDB_PASS = os.getenv("FALKORDB_PASSWORD", "")


def build_cypher_params_header(params: Optional[Dict[str, Any]]) -> str:
    """Constructs native FalkorDB parameterized query header (CYPHER `k`=v ...)."""
    if not params:
        return ""
    parts = []
    for k, v in params.items():
        parts.append(f"`{k}`={stringify_param_value(v)}")
    return "CYPHER " + " ".join(parts) + " "


def _format_cypher_val(v: Any) -> str:
    """Recursively formats a Python value into Cypher literal format."""
    if v is None:
        return "null"
    if isinstance(v, bool):
        return "true" if v else "false"
    if isinstance(v, (int, float)):
        return str(v)
    if isinstance(v, str):
        escaped_v = v.replace("\\", "\\\\").replace("'", "\\'").replace('"', '\\"')
        return f"'{escaped_v}'"
    if isinstance(v, dict):
        elements = [f"{k}: {_format_cypher_val(val)}" for k, val in v.items()]
        return "{" + ", ".join(elements) + "}"
    if isinstance(v, (list, tuple, set)):
        elements = [_format_cypher_val(item) for item in v]
        return "[" + ", ".join(elements) + "]"
    escaped = str(v).replace("\\", "\\\\").replace("'", "\\'").replace('"', '\\"')
    return f"'{escaped}'"


_CYPHER_TOKEN_PATTERN = re.compile(
    r"(?P<quote>'(?:[^'\\]|\\.)*'|\"(?:[^\"\\]|\\.)*\"|`(?:[^`\\]|\\.)*`)|"
    r"(?P<comment>//[^\r\n]*|/\*[\s\S]*?\*/)|"
    r"\$(?P<param>[a-zA-Z_][a-zA-Z0-9_]*)"
)


def format_cypher_query(cypher: str, params: Optional[Dict[str, Any]] = None) -> str:
    """
    Interpolates parameters into a Cypher query string with token-safe single-pass substitution,
    preventing double-substitution, key collisions, and replacement inside string literals or comments.
    """
    if not params:
        return cypher

    def _replace_token(match: re.Match[str]) -> str:
        param_name = match.group("param")
        if param_name is not None and param_name in params:
            return _format_cypher_val(params[param_name])
        return match.group(0)

    return _CYPHER_TOKEN_PATTERN.sub(_replace_token, cypher)



_USE_DEFAULT_SOCKET = object()


class FalkorDBClient:
    """Canonical FalkorDB Redis client with robust query execution and indexing."""

    def __init__(
        self,
        host: str = FALKORDB_HOST,
        port: int = FALKORDB_PORT,
        password: Optional[str] = FALKORDB_PASS,
        socket_path: Any = _USE_DEFAULT_SOCKET,
    ):
        self.host = host
        self.port = port
        self.password = password or None
        self.socket_path = get_default_socket() if socket_path is _USE_DEFAULT_SOCKET else socket_path
        self._r: Optional[redis.Redis] = None
        self._verified_indexes: Set[Tuple[str, str, str]] = set()
        self._resolved_graphs: Dict[str, str] = {}

    def get_redis(self) -> redis.Redis:
        """Returns active Redis client connection, preferring Unix domain socket."""
        if self._r is not None:
            return self._r

        # Attempt 1: Unix Domain Socket (Ultra-low latency IPC)
        if self.socket_path and Path(self.socket_path).is_socket():
            try:
                r = redis.Redis(
                    unix_socket_path=str(self.socket_path),
                    password=self.password,
                    decode_responses=True,
                    socket_timeout=5.0,
                )
                r.ping()
                self._r = r
                return self._r
            except Exception:
                pass

        # Attempt 2: TCP Loopback / Remote Endpoint
        self._r = redis.Redis(
            host=self.host,
            port=self.port,
            password=self.password,
            decode_responses=True,
            socket_timeout=5.0,
        )
        return self._r

    def resolve_graph_name(self, graph_name: str) -> str:
        """Accept both 'kortext' and 'cerebrum' names for seamless backward-compatibility with existing on-disk data."""
        if graph_name not in ("kortext", "cerebrum", "kortext_symbols", "cerebrum_symbols"):
            return graph_name
        if graph_name in self._resolved_graphs:
            return self._resolved_graphs[graph_name]
        try:
            client = self.get_redis()
            existing_graphs = client.execute_command("GRAPH.LIST")
            if isinstance(existing_graphs, list):
                existing_graphs_str = [g.decode() if isinstance(g, bytes) else str(g) for g in existing_graphs]
                if graph_name in existing_graphs_str:
                    self._resolved_graphs[graph_name] = graph_name
                    return graph_name
                if graph_name == "kortext" and "cerebrum" in existing_graphs_str:
                    self._resolved_graphs[graph_name] = "cerebrum"
                    return "cerebrum"
                if graph_name == "kortext_symbols" and "cerebrum_symbols" in existing_graphs_str:
                    self._resolved_graphs[graph_name] = "cerebrum_symbols"
                    return "cerebrum_symbols"
                if graph_name == "cerebrum" and "kortext" in existing_graphs_str:
                    self._resolved_graphs[graph_name] = "kortext"
                    return "kortext"
                if graph_name == "cerebrum_symbols" and "kortext_symbols" in existing_graphs_str:
                    self._resolved_graphs[graph_name] = "kortext_symbols"
                    return "kortext_symbols"
        except Exception:
            pass
        self._resolved_graphs[graph_name] = graph_name
        return graph_name

    def ensure_indexes(self, graph_name: str, indexes: List[Tuple[str, str]]):
        """
        Ensures B-tree schema indexes on specified labels and properties.
        indexes: list of (node_label, property_name)
        """
        resolved_graph = self.resolve_graph_name(graph_name)
        client = self.get_redis()
        for label, prop in indexes:
            key = (resolved_graph, label, prop)
            if key in self._verified_indexes:
                continue
            try:
                client.execute_command("GRAPH.QUERY", resolved_graph, f"CREATE INDEX FOR (n:{label}) ON (n.{prop})")
                self._verified_indexes.add(key)
            except Exception:
                self._verified_indexes.add(key)

    def query(
        self,
        graph_name: str,
        cypher: str,
        params: Optional[Dict[str, Any]] = None,
        attempts: int = 2,
        read_only: bool = False,
    ) -> List[List[Any]]:
        """
        Executes a Cypher query on the specified graph with native parameter binding and reconnect.
        """
        resolved_graph = self.resolve_graph_name(graph_name)
        if params and not cypher.lstrip().startswith("CYPHER "):
            query_str = build_cypher_params_header(params) + cypher
        else:
            query_str = cypher

        client = self.get_redis()
        cmd = "GRAPH.RO_QUERY" if read_only else "GRAPH.QUERY"

        for attempt in range(attempts):
            try:
                res = client.execute_command(cmd, resolved_graph, query_str)
                return res if res and isinstance(res, list) else []
            except (redis.ConnectionError, redis.TimeoutError):
                self._r = None
                client = self.get_redis()
                if attempt == attempts - 1:
                    raise
            except Exception as e:
                logger.error("[FalkorDBClient] Error executing query on '%s': %s", graph_name, e)
                return []
        return []


_SINGLETON_CLIENT: Optional[FalkorDBClient] = None


def get_shared_falkordb_client(
    host: str = FALKORDB_HOST,
    port: int = FALKORDB_PORT,
    password: Optional[str] = FALKORDB_PASS,
) -> FalkorDBClient:
    """Returns singleton FalkorDBClient instance."""
    global _SINGLETON_CLIENT
    if _SINGLETON_CLIENT is None:
        _SINGLETON_CLIENT = FalkorDBClient(host=host, port=port, password=password)
    return _SINGLETON_CLIENT
