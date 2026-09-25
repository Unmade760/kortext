"""
AST Grounding Hashes and Invariant Drift Detection (The MEX Pattern).

Grounds abstract architectural rules and invariants to concrete code symbols
and their AST body SHA-256 hashes:
    Invariant(R) grounds_to (symbol_id, SHA256(AST_body))

When code under the invariant changes, the AST body hash diverges, flagging
the invariant as DRIFTED / STALE.
"""
from __future__ import annotations

import hashlib
import json
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

from cerebrum.chunking.ast_extractor import get_body_node, get_identifier
from cerebrum.chunking.languages import LANG_MAP, Parser
from cerebrum.falkordb_client import FalkorDBClient, FALKORDB_HOST, FALKORDB_PORT, FALKORDB_PASS

CEREBRUM_ROOT = Path(__file__).resolve().parent.parent
JOURNAL_DIR = Path(os.getenv("JOURNAL_DIR", str(CEREBRUM_ROOT / "journal")))
GROUNDED_FILE = JOURNAL_DIR / "grounded_invariants.json"
QUARANTINE_DIR = JOURNAL_DIR / "quarantine"
FALKORDB_DB = os.getenv("FALKORDB_DATABASE", "cerebrum")


def compute_ast_body_hash(file_path: str, symbol_name: str) -> Optional[str]:
    """
    Parses a source file with Tree-sitter, finds the node for symbol_name,
    and returns the SHA-256 hash of its normalized AST body bytes.
    """
    p = Path(file_path).resolve()
    if not p.exists() or not p.is_file():
        return None

    ext = p.suffix.lower()
    lang = LANG_MAP.get(ext)
    if not lang:
        return None

    try:
        source_bytes = p.read_bytes()
        parser = Parser(lang)
        tree = parser.parse(source_bytes)
    except Exception:
        return None

    target = symbol_name.lower().strip()

    # Search BFS/DFS for symbol definition
    stack = [tree.root_node]
    matching_node = None

    while stack:
        curr = stack.pop()
        ident = get_identifier(curr, source_bytes)
        if ident and ident.lower() == target:
            # Prefer function/class/method/struct definitions
            if any(k in curr.type for k in ("function", "class", "method", "struct", "impl", "interface", "type")):
                matching_node = curr
                break
            if matching_node is None:
                matching_node = curr

        for child in reversed(curr.children):
            stack.append(child)

    if not matching_node:
        return None

    body = get_body_node(matching_node)
    if body:
        body_bytes = source_bytes[body.start_byte:body.end_byte]
    else:
        body_bytes = source_bytes[matching_node.start_byte:matching_node.end_byte]

    # Normalize whitespace before hashing
    normalized = b" ".join(body_bytes.split())
    return hashlib.sha256(normalized).hexdigest()


class InvariantGroundingEngine:
    """Manages invariant grounding, drift detection, and quarantine."""

    def __init__(
        self,
        host: str = FALKORDB_HOST,
        port: int = FALKORDB_PORT,
        password: Optional[str] = FALKORDB_PASS,
        db_name: str = FALKORDB_DB,
    ):
        self.host = host
        self.port = port
        self.password = password or None
        self.db_name = db_name
        self.client = FalkorDBClient(host=self.host, port=self.port, password=self.password)
        QUARANTINE_DIR.mkdir(parents=True, exist_ok=True)

    def _query(self, cypher: str, params: Optional[Dict[str, Any]] = None) -> List[List[Any]]:
        return self.client.query(self.db_name, cypher, params)

    def load_grounded_invariants(self) -> List[Dict[str, Any]]:
        """Loads grounded invariant records from disk."""
        if not GROUNDED_FILE.exists():
            return []
        try:
            with open(GROUNDED_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            return []

    def save_grounded_invariants(self, invariants: List[Dict[str, Any]]):
        """Saves grounded invariant records to disk."""
        GROUNDED_FILE.parent.mkdir(parents=True, exist_ok=True)
        with open(GROUNDED_FILE, "w", encoding="utf-8") as f:
            json.dump(invariants, f, indent=2)

    def ground_invariant(
        self,
        domain: str,
        rule: str,
        rationale: str,
        symbol_name: str,
        file_path: str,
        trust_level: str = "speculative",
    ) -> Dict[str, Any]:
        """
        Grounds an architectural invariant to a live code symbol and its AST body hash.
        """
        now = datetime.now(timezone.utc).isoformat()
        resolved_path = str(Path(file_path).resolve())
        ast_hash = compute_ast_body_hash(resolved_path, symbol_name)

        record = {
            "domain": domain,
            "rule": rule,
            "rationale": rationale,
            "symbol_name": symbol_name,
            "file_path": resolved_path,
            "ast_hash": ast_hash,
            "status": "active" if ast_hash else "unresolved_symbol",
            "trust_level": trust_level,
            "grounded_at": now,
            "last_verified": now,
        }

        # Update JSON store
        items = self.load_grounded_invariants()
        # Replace if rule exists, otherwise append
        updated = False
        for i, item in enumerate(items):
            if item.get("rule") == rule:
                items[i] = record
                updated = True
                break
        if not updated:
            items.append(record)
        self.save_grounded_invariants(items)

        # Update FalkorDB
        self._query(
            "MERGE (i:Invariant {rule: $rule}) "
            "SET i.domain = $domain, i.rationale = $rationale, i.symbol = $symbol, "
            "    i.file_path = $file, i.ast_hash = $hash, i.status = $status, "
            "    i.trust_level = $trust_level, i.updated_at = $now",
            {
                "rule": rule,
                "domain": domain,
                "rationale": rationale,
                "symbol": symbol_name,
                "file": resolved_path,
                "hash": ast_hash or "",
                "status": record["status"],
                "trust_level": trust_level,
                "now": now,
            },
        )

        return record

    def audit_invariant_drift(self, quarantine_drifted: bool = False) -> Dict[str, Any]:
        """
        Audits all grounded invariants against live codebase AST body hashes.
        Detects drifted, verified, and orphaned invariants.
        """
        now = datetime.now(timezone.utc).isoformat()
        items = self.load_grounded_invariants()

        verified: List[Dict[str, Any]] = []
        drifted: List[Dict[str, Any]] = []
        orphaned: List[Dict[str, Any]] = []

        for item in items:
            file_path = item.get("file_path", "")
            symbol_name = item.get("symbol_name", "")
            recorded_hash = item.get("ast_hash")

            p = Path(file_path)
            if not p.exists():
                item["status"] = "orphaned_file"
                orphaned.append(item)
                continue

            live_hash = compute_ast_body_hash(file_path, symbol_name)
            if not live_hash:
                item["status"] = "orphaned_symbol"
                orphaned.append(item)
            elif live_hash == recorded_hash:
                item["status"] = "verified"
                item["last_verified"] = now
                verified.append(item)
            else:
                item["status"] = "drifted"
                item["drifted_at"] = now
                item["live_hash"] = live_hash
                drifted.append(item)

        if quarantine_drifted and drifted:
            quarantine_file = QUARANTINE_DIR / f"{datetime.now().strftime('%Y-%m-%d_%H%M')}_quarantine.json"
            with open(quarantine_file, "w", encoding="utf-8") as qf:
                json.dump(drifted, qf, indent=2)

        self.save_grounded_invariants(items)

        return {
            "total_grounded": len(items),
            "verified_count": len(verified),
            "drifted_count": len(drifted),
            "orphaned_count": len(orphaned),
            "verified": verified,
            "drifted": drifted,
            "orphaned": orphaned,
        }
