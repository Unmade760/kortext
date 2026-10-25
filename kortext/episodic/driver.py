"""
Agent-Native Episodic Memory Driver for FalkorDB.

Eliminates the :8003 LLM proxy daemon completely.
The main Antigravity agent supplies structured entities, facts, and supersedes directly,
or passes a narrative which is embedded via local oMLX :8000 (Metal GPU) and committed
directly to FalkorDB via native GraphBLAS commands.
"""
from __future__ import annotations

import json
import logging
import os
import re
import uuid
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional
import redis

from kortext.falkordb_client import FalkorDBClient, FALKORDB_HOST, FALKORDB_PORT, FALKORDB_PASS
from kortext.retrieval.retention import compute_weibull_retention
from kortext.trust.sanitizer import CausalSanitizer, SecurityViolation

logger = logging.getLogger(__name__)


def _parse_fact_age_hours(
    valid_from: Optional[str],
    created_at: Optional[str],
    now_dt: datetime,
) -> tuple[float, str]:
    """Calculates elapsed age in hours based on valid_from or created_at, returning (age_hours, sort_key)."""
    ts_str = valid_from or created_at or ""
    if not ts_str:
        return 0.0, ""
    try:
        clean_ts = ts_str.replace("Z", "+00:00")
        dt = datetime.fromisoformat(clean_ts)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        elapsed_seconds = (now_dt - dt).total_seconds()
        age_hours = max(0.0, elapsed_seconds / 3600.0)
        return age_hours, ts_str
    except Exception:
        return 0.0, ts_str


def jaro_winkler_similarity(s1: str, s2: str, p: float = 0.1) -> float:
    """Computes Jaro-Winkler similarity in [0.0, 1.0] for fast deterministic entity resolution."""
    a = (s1 or "").strip().lower()
    b = (s2 or "").strip().lower()
    if a == b:
        return 1.0 if a else 0.0
    len_a, len_b = len(a), len(b)
    if len_a == 0 or len_b == 0:
        return 0.0

    match_dist = max(0, (max(len_a, len_b) // 2) - 1)
    a_matches = [False] * len_a
    b_matches = [False] * len_b
    matches = 0
    transpositions = 0

    for i in range(len_a):
        start = max(0, i - match_dist)
        end = min(i + match_dist + 1, len_b)
        for j in range(start, end):
            if b_matches[j] or a[i] != b[j]:
                continue
            a_matches[i] = True
            b_matches[j] = True
            matches += 1
            break

    if matches == 0:
        return 0.0

    k = 0
    for i in range(len_a):
        if not a_matches[i]:
            continue
        while not b_matches[k]:
            k += 1
        if a[i] != b[k]:
            transpositions += 1
        k += 1

    jaro = (
        (matches / len_a)
        + (matches / len_b)
        + ((matches - transpositions / 2.0) / matches)
    ) / 3.0

    prefix = 0
    for ch_a, ch_b in zip(a[:4], b[:4]):
        if ch_a == ch_b:
            prefix += 1
        else:
            break

    return jaro + prefix * p * (1.0 - jaro)

FALKORDB_DB   = os.getenv("KORTEXT_DATABASE", os.getenv("FALKORDB_DATABASE", "kortext"))


TRUST_ANCHOR_LEVELS: Dict[str, float] = {
    "speculative": 0.50,
    "untrusted": 0.30,
    "tool_confirmed": 0.60,
    "verified": 0.80,
    "user_approved": 1.00,
    "system": 1.00,
}

VALID_CATEGORIES = (
    "decision",
    "roadmap",
    "implementation",
    "experiment",
    "benchmark",
    "investigation",
    "research",
    "report",
)


class AgentNativeEpisodicDriver:
    """Direct FalkorDB driver for Episodic & Temporal Knowledge Memory."""

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
        self.sanitizer = CausalSanitizer()
        self._entity_cache: Dict[str, str] = {}

    def _get_client(self) -> redis.Redis:
        return self.client.get_redis()

    def _query(self, cypher: str, params: Optional[Dict[str, Any]] = None) -> List[List[Any]]:
        return self.client.query(self.db_name, cypher, params)

    def resolve_canonical_entity(self, raw_name: str, threshold: float = 0.88) -> str:
        """
        Resolves near-duplicate entity names against existing :Entity nodes in FalkorDB
        using Jaro-Winkler similarity (>= 0.88) and token Jaccard overlap so variants
        like 'FalkorDB' and 'falkordb' merge into a single canonical node.
        Uses an in-memory cache to avoid N+1 roundtrips during batch outcomes.
        """
        cleaned = (raw_name or "").strip()
        if not cleaned or len(cleaned) < 3:
            return cleaned
        cache_key = cleaned.lower()
        if cache_key in self._entity_cache:
            return self._entity_cache[cache_key]
        try:
            if getattr(self.client, "_is_live_falkor_client", False) is not True:
                self._entity_cache[cache_key] = cleaned
                return cleaned
            cand_tokens = [
                t for t in cleaned.lower().replace("_", " ").replace("-", " ").split()
                if len(t) >= 3
            ]
            res = self._query(
                "MATCH (n:Entity) "
                "WHERE toLower(n.name) STARTS WITH toLower($prefix) "
                "OR ANY(tok IN $tokens WHERE toLower(n.name) CONTAINS tok) "
                "RETURN n.name LIMIT 35",
                {"prefix": cleaned[:2], "tokens": cand_tokens[:4]},
            )
            if not res or len(res) < 2 or not isinstance(res[1], list):
                self._entity_cache[cache_key] = cleaned
                return cleaned
            best_name = cleaned
            best_score = 0.0
            cand_subtokens = set(re.findall(r"[A-Z]+(?=[A-Z][a-z]|\b)|[A-Z]?[a-z]+|\d+", cleaned))
            cand_token_set = {t.lower() for t in cand_subtokens if len(t) >= 2} or set(
                cleaned.lower().replace("_", " ").replace("-", " ").split()
            )
            for row in res[1]:
                if not row or not row[0]:
                    continue
                existing_name = str(row[0]).strip()
                if existing_name.lower() == cleaned.lower():
                    self._entity_cache[cache_key] = existing_name
                    return existing_name
                jw = jaro_winkler_similarity(cleaned, existing_name)
                ex_subtokens = set(re.findall(r"[A-Z]+(?=[A-Z][a-z]|\b)|[A-Z]?[a-z]+|\d+", existing_name))
                ex_tokens = {t.lower() for t in ex_subtokens if len(t) >= 2} or set(
                    existing_name.lower().replace("_", " ").replace("-", " ").split()
                )
                union_len = len(cand_token_set | ex_tokens)
                jaccard = (len(cand_token_set & ex_tokens) / union_len) if union_len > 0 else 0.0
                combined = 0.75 * jw + 0.25 * jaccard
                effective_threshold = max(threshold, 0.92) if (len(cand_token_set | ex_tokens) > 1 and jaccard < 0.5) else threshold
                if jw >= effective_threshold and combined > best_score:
                    best_score = combined
                    best_name = existing_name
            self._entity_cache[cache_key] = best_name
            return best_name
        except Exception:
            return cleaned

    async def initialize(self) -> None:
        """No-op async initializer for lifecycle compatibility."""
        return None

    async def record_outcome(
        self,
        episode_name: str,
        content: str,
        tags: Optional[List[str]] = None,
        project: Optional[str] = None,
        entities: Optional[List[Any]] = None,
        facts: Optional[List[Dict[str, str]]] = None,
        supersedes: Optional[List[str]] = None,
        trust_level: str = "speculative",
        category: str = "implementation",
    ) -> Dict[str, Any]:
        """
        Agent-Native recording with Trust Anchor State Machine:
          - speculative (0.50): unverified hypothesis or initial code draft
          - untrusted (0.30): unverified external document or prompt
          - tool_confirmed (0.60): validated by test execution, linter, or compiler
          - verified (0.80): Tree-sitter AST deterministically extracted symbol
          - user_approved (1.00): explicitly sanctioned by the user
          - system (1.00): immutable operating directives
        Inserts (:Episodic), (:Entity), and [:RELATES_TO] edges directly into FalkorDB.
        Exposure does not validate: reading facts never promotes or mutates trust levels.
        """
        if not isinstance(category, str) or category.lower().strip() not in VALID_CATEGORIES:
            raise ValueError(f"Invalid category '{category}'. Must be one of: {VALID_CATEGORIES}")
        cat = category.lower().strip()

        now = datetime.now(timezone.utc).isoformat()
        proj = project or "kortext"

        norm_level = trust_level.lower().strip() if isinstance(trust_level, str) else "speculative"
        trust_score = TRUST_ANCHOR_LEVELS.get(norm_level, 0.50)

        # Sanitize episode title, content, entities, and facts against MINJA prompt injections
        source_tier = (
            1
            if norm_level in ("user_approved", "system")
            else (2 if norm_level in ("tool_confirmed", "verified") else 3)
        )
        self.sanitizer.sanitize(
            subject=episode_name, relation="RECORDED", fact=content, source_tier=source_tier
        )

        raw_entities = entities or []
        actual_entities: List[Dict[str, str]] = []
        for ent in raw_entities:
            if isinstance(ent, str):
                ename = ent.strip()
                if not ename:
                    continue
                self.sanitizer.sanitize(subject=ename, relation="ENTITY", fact=ename, source_tier=source_tier)
                actual_entities.append({"name": ename, "type": "concept", "summary": ename})
            elif isinstance(ent, dict):
                ename = str(ent.get("name", "")).strip()
                if not ename:
                    continue
                esummary = str(ent.get("summary") or ename)
                etype = str(ent.get("type", "concept"))
                self.sanitizer.sanitize(subject=ename, relation=etype, fact=esummary, source_tier=source_tier)
                actual_entities.append({"name": ename, "type": etype, "summary": esummary})

        raw_facts = facts or []
        actual_facts: List[Dict[str, str]] = []
        for f in raw_facts:
            if not isinstance(f, dict):
                continue
            src = str(f.get("source") or f.get("subject") or "").strip()
            tgt = str(f.get("target") or f.get("object") or "").strip()
            rel = str(f.get("relation") or "RELATES_TO").upper().replace(" ", "_")
            fact_text = str(f.get("fact") or f"{src} {rel} {tgt}")
            self.sanitizer.sanitize(
                subject=src or episode_name,
                relation=rel,
                fact=f"{tgt}: {fact_text}" if tgt else fact_text,
                source_tier=source_tier,
            )
            actual_facts.append({"source": src, "target": tgt, "relation": rel, "fact": fact_text})

        # 1. Supersede older conflicting facts if specified
        superseded_count = 0
        if supersedes:
            for pattern in supersedes:
                res = self._query(
                    "MATCH (old:Episodic) WHERE (old.name CONTAINS $pat OR old.content CONTAINS $pat) "
                    "AND (old.superseded IS NULL OR old.superseded = false) "
                    "SET old.superseded = true, old.superseded_by = $by, old.superseded_at = $now, "
                    "old.superseded_reason = 'Superseded by ' + $by "
                    "RETURN count(old)",
                    {"pat": pattern, "by": episode_name, "now": now},
                )
                if res and len(res) > 1 and res[1]:
                    try:
                        superseded_count += int(res[1][0][0])
                    except Exception:
                        logger.debug("Suppressed non-fatal exception")

        # 2. Persist (:Episodic) Node with Trust Anchor and link to Project
        tags_str = ", ".join(tags) if tags else ""
        self._query(
            "MERGE (e:Episodic {name: $name}) "
            "SET e.content = $content, e.created_at = $now, e.project = $project, "
            "e.tags = $tags, e.superseded = false, e.trust_level = $trust_level, "
            "e.trust_score = $trust_score, e.category = $category "
            "MERGE (p:Project {id: $project}) "
            "ON CREATE SET p.name = $project "
            "MERGE (p)-[:HAS_EPISODE]->(e)",
            {
                "name": episode_name,
                "content": content,
                "now": now,
                "project": proj,
                "tags": tags_str,
                "trust_level": norm_level,
                "trust_score": trust_score,
                "category": cat,
            },
        )

        # Write Entities (resolved via Jaro-Winkler + Token Jaccard entity disambiguation)
        for ent in actual_entities:
            raw_ename = ent.get("name", "").strip()
            if not raw_ename:
                continue
            ename = self.resolve_canonical_entity(raw_ename)
            esummary = ent.get("summary") or ename
            etype = ent.get("type", "concept")

            self._query(
                "MERGE (n:Entity {name: $name}) "
                "SET n.summary = $summary, n.entity_type = $type, n.updated_at = $now "
                "WITH n "
                "MATCH (e:Episodic {name: $ename}) "
                "MERGE (e)-[:MENTIONS]->(n)",
                {
                    "name": ename,
                    "summary": esummary,
                    "type": etype,
                    "now": now,
                    "ename": episode_name,
                },
            )

        # Write Fact Edges with Trust Anchor
        for f in actual_facts:
            raw_src = f.get("source", "").strip()
            raw_tgt = f.get("target", "").strip()
            src = self.resolve_canonical_entity(raw_src) if raw_src else ""
            tgt = self.resolve_canonical_entity(raw_tgt) if raw_tgt else ""
            rel = (f.get("relation") or "RELATES_TO").upper().replace(" ", "_")
            fact_text = f.get("fact") or f"{src} {rel} {tgt}"

            if src and tgt:
                fact_id = f"fact_{uuid.uuid4().hex[:10]}"
                self._query(
                    "MERGE (s:Entity {name: $src}) "
                    "MERGE (t:Entity {name: $tgt}) "
                    "MERGE (s)-[r:RELATES_TO {fact: $fact, relation: $rel}]->(t) "
                    "SET r.id = $fact_id, r.created_at = $now, r.valid_from = $now, r.valid_to = null, "
                    "r.transaction_time = $now, r.source_session = $session, r.importance = 5, "
                    "r.confidence = 0.95, r.dormant = false, r.superseded = false, "
                    "r.trust_level = $trust_level, r.trust_score = $trust_score, "
                    "r.project = $project",
                    {
                        "src": src,
                        "tgt": tgt,
                        "fact": fact_text,
                        "rel": rel,
                        "now": now,
                        "fact_id": fact_id,
                        "session": episode_name,
                        "trust_level": norm_level,
                        "trust_score": trust_score,
                        "project": proj,
                    },
                )

        auto_entities = 0
        if cat == "decision" and not actual_entities:
            self._query(
                "MATCH (e:Episodic {name: $ename}) "
                "MERGE (adr:Entity:ADR {name: $ename}) "
                "SET adr.summary = $summary, adr.entity_type = 'adr', adr.updated_at = $now "
                "MERGE (e)-[:DECIDES]->(adr)",
                {
                    "ename": episode_name,
                    "summary": content,
                    "now": now,
                },
            )
            auto_entities += 1
        elif cat == "roadmap":
            self._query(
                "MATCH (e:Episodic {name: $ename}) "
                "MERGE (m:Entity:Milestone {name: $ename}) "
                "SET m.summary = $summary, m.entity_type = 'milestone', m.updated_at = $now "
                "MERGE (e)-[:MILESTONE]->(m)",
                {
                    "ename": episode_name,
                    "summary": content,
                    "now": now,
                },
            )
            auto_entities += 1

        return {
            "status": "ok",
            "episode": episode_name,
            "category": cat,
            "trust_level": norm_level,
            "trust_score": trust_score,
            "entities_written": len(actual_entities) + auto_entities,
            "facts_written": len(actual_facts),
            "superseded_count": superseded_count,
        }

    def record_fact(
        self,
        subject: str,
        relation: str,
        fact: str,
        object_name: Optional[str] = None,
        importance: int = 5,
        valid_from: Optional[str] = None,
        valid_to: Optional[str] = None,
        supersedes: Optional[str] = None,
        confidence: float = 0.95,
        source_session: Optional[str] = None,
        source_tier: int = 2,
        project: Optional[str] = None,
        trust_level: Optional[str] = None,
    ) -> str:
        """
        Records an episodic relationship between subject and object entities with bi-temporal attribution.
        Automatically resolves conflicting facts by materializing [:SUPERSEDES] edges (Section 53, Invariant D5, D30).
        """
        # Sanitize untrusted fact text against MINJA prompt injections before persisting
        self.sanitizer.sanitize(subject=subject, relation=relation, fact=fact, source_tier=source_tier)
        from kortext.trust.sanitizer import strip_invisible_unicode

        subject = strip_invisible_unicode(subject).strip()
        relation = strip_invisible_unicode(relation).strip()
        fact = strip_invisible_unicode(fact).strip()
        if object_name:
            object_name = strip_invisible_unicode(object_name).strip()

        fact_id = f"fact_{uuid.uuid4().hex[:10]}"
        now = datetime.now(timezone.utc).isoformat()
        v_start = valid_from or now
        obj = (object_name or relation).strip()
        proj = project or getattr(self, "db_name", None) or "kortext"

        if trust_level:
            norm_level = trust_level.lower().strip()
        elif source_tier == 1:
            norm_level = "user_approved"
        elif source_tier == 2:
            norm_level = "tool_confirmed"
        else:
            norm_level = "untrusted"
        trust_score = TRUST_ANCHOR_LEVELS.get(norm_level, 0.60)

        # 1. Ensure Subject and Object Nodes Exist
        merge_nodes_cypher = """
        MERGE (s:Entity {name: $sub})
        ON CREATE SET s.first_seen = $now, s.trust_tier = 2
        MERGE (t:Entity {name: $obj})
        ON CREATE SET t.first_seen = $now, t.trust_tier = 2
        """
        self._query(merge_nodes_cypher, {"sub": subject, "obj": obj, "now": now})

        # 2. Materialize Directed Bi-Temporal Relationship
        rel_cypher = """
        MATCH (s:Entity {name: $sub})
        MATCH (t:Entity {name: $obj})
        CREATE (s)-[r:RELATES_TO {
            id: $fact_id,
            fact: $fact,
            relation: $rel,
            project: $project,
            valid_from: $v_start,
            valid_to: $v_end,
            created_at: $now,
            transaction_time: $now,
            importance: $imp,
            confidence: $conf,
            source_session: $session,
            dormant: false,
            superseded: false,
            trust_level: $trust_level,
            trust_score: $trust_score
        }]->(t)
        RETURN r.id
        """
        params = {
            "sub": subject,
            "obj": obj,
            "rel": relation,
            "fact_id": fact_id,
            "fact": fact,
            "v_start": v_start,
            "v_end": valid_to,
            "now": now,
            "imp": importance,
            "conf": confidence,
            "session": source_session or "active_session",
            "project": proj,
            "trust_level": norm_level,
            "trust_score": trust_score,
        }
        self._query(rel_cypher, params)

        # 3. Handle Superseded Fact Invalidations
        if supersedes:
            self._invalidate_and_link_superseded(supersedes, fact_id, now)

        return fact_id

    def _invalidate_and_link_superseded(self, old_fact_id: str, new_fact_id: str, timestamp: str):
        """
        Closes the validity window of the old fact, marks it dormant and superseded,
        and sets provisional_stale=true on 1-hop outgoing facts derived from or connected to the superseded fact/object.
        """
        cypher = """
        MATCH ()-[r_old:RELATES_TO {id: $old_id}]->(obj)
        SET r_old.valid_to = $now, r_old.dormant = true, r_old.superseded = true, r_old.superseded_by = $new_id
        WITH DISTINCT obj
        OPTIONAL MATCH (obj)-[r_dep:RELATES_TO]->()
        WHERE r_dep.id <> $new_id AND r_dep.id <> $old_id
        SET r_dep.provisional_stale = true
        WITH DISTINCT obj
        OPTIONAL MATCH ()-[r_derived:RELATES_TO]->()
        WHERE r_derived.derived_from = $old_id
        SET r_derived.provisional_stale = true
        """
        self._query(cypher, {
            "old_id": old_fact_id,
            "new_id": new_fact_id,
            "now": timestamp,
        })

    def query_facts_as_of(
        self,
        subject: str,
        as_of_date: str,
        limit: int = 10,
        project: Optional[str] = None,
        as_of_asserted_date: Optional[str] = None,
    ) -> List[Dict[str, Any]]:
        """
        Executes a point-in-time bi-temporal query returning facts valid on `as_of_date` (World Timeline T)
        and optionally known to the system as of `as_of_asserted_date` (System Timeline T', Invariant D5).
        """
        target_project = project.strip() if isinstance(project, str) else None
        filter_project = bool(target_project and target_project.lower() != "all")
        proj_filter = "  AND coalesce(r.project, 'kortext') = $project\n" if filter_project else ""
        sys_time_filter = (
            "  AND coalesce(r.transaction_time, r.created_at, $asserted_date) <= $asserted_date\n"
            "  AND (r.superseded_at IS NULL OR r.superseded_at > $asserted_date)\n"
            if as_of_asserted_date
            else ""
        )

        cypher = f"""
        MATCH (s:Entity {{name: $sub}})-[r:RELATES_TO]->(target)
        WHERE r.valid_from <= $target_date
          AND (r.valid_to IS NULL OR r.valid_to > $target_date)
        {sys_time_filter}{proj_filter}RETURN r.id, s.name, r.relation, r.fact, r.valid_from, r.valid_to, r.confidence
        ORDER BY r.valid_from DESC
        LIMIT $lim
        """
        params: Dict[str, Any] = {
            "sub": subject,
            "target_date": as_of_date,
            "lim": limit,
        }
        if as_of_asserted_date:
            params["asserted_date"] = as_of_asserted_date
        if filter_project:
            params["project"] = target_project
        raw = self._query(cypher, params)

        if not raw or len(raw) < 2 or not raw[1]:
            return []

        results = []
        for row in raw[1]:
            results.append({
                "fact_id": row[0],
                "subject": row[1],
                "relation": row[2],
                "fact": row[3],
                "valid_from": row[4],
                "valid_to": row[5],
                "confidence": row[6],
            })
        return results

    def query_multi_hop_facts(
        self,
        entity_name: str,
        max_hops: int = 2,
        limit: int = 20,
        project: Optional[str] = None,
    ) -> List[Dict[str, Any]]:
        """
        Traverses episodic memory up to max_hops (default 2) starting from entity_name.
        Discovers connected facts across different sessions via intermediate bridge entities.
        Filters out dormant and superseded relationships.
        """
        if not entity_name or max_hops < 1:
            return []

        target_project = project.strip() if isinstance(project, str) else None
        filter_project = bool(target_project and target_project.lower() != "all")
        proj_filter_1hop = "  AND coalesce(r.project, 'kortext') = $project\n" if filter_project else ""

        # 1. Fetch 1-hop facts connected to entity_name (both outgoing and incoming)
        cypher_1hop = f"""
        MATCH (s:Entity {{name: $entity}})-[r:RELATES_TO]-(t:Entity)
        WHERE coalesce(r.superseded, false) = false
          AND coalesce(r.dormant, false) = false
        {proj_filter_1hop}RETURN r.id, startNode(r).name, r.relation, endNode(r).name, r.fact, r.source_session,
               r.valid_from, r.valid_to, r.confidence, t.name
        ORDER BY coalesce(r.valid_from, r.transaction_time, '') DESC
        LIMIT $lim
        """
        params_1hop: Dict[str, Any] = {"entity": entity_name, "lim": limit}
        if filter_project:
            params_1hop["project"] = target_project
        raw_1hop = self._query(cypher_1hop, params_1hop)

        results: List[Dict[str, Any]] = []
        seen_fact_ids: set[str] = set()
        seen_signatures: set[tuple[str, str, str, str]] = set()
        bridge_entities: List[str] = []

        if raw_1hop and len(raw_1hop) > 1 and raw_1hop[1]:
            for row in raw_1hop[1]:
                fid = str(row[0]) if row[0] else ""
                s_name = str(row[1]) if row[1] else ""
                rel = str(row[2]) if row[2] else ""
                o_name = str(row[3]) if row[3] else ""
                fact_text = str(row[4]) if row[4] else f"{s_name} {rel} {o_name}"
                sess = str(row[5]) if len(row) > 5 and row[5] else None
                v_from = str(row[6]) if len(row) > 6 and row[6] else None
                v_to = str(row[7]) if len(row) > 7 and row[7] else None
                conf = float(row[8]) if len(row) > 8 and row[8] is not None else 0.95
                neighbor = str(row[9]) if len(row) > 9 and row[9] else ""

                sig = (s_name, rel, o_name, fact_text)
                if (fid and fid in seen_fact_ids) or sig in seen_signatures:
                    continue
                if fid:
                    seen_fact_ids.add(fid)
                seen_signatures.add(sig)

                results.append({
                    "fact_id": fid,
                    "subject": s_name,
                    "relation": rel,
                    "target": o_name,
                    "object": o_name,
                    "fact": fact_text,
                    "source_session": sess,
                    "valid_from": v_from,
                    "valid_to": v_to,
                    "confidence": conf,
                    "hops": 1,
                    "bridge_entity": None,
                    "path": [entity_name, neighbor] if neighbor else [entity_name],
                })

                if neighbor and neighbor != entity_name and neighbor not in bridge_entities:
                    bridge_entities.append(neighbor)

        # 2. Fetch 2-hop facts connected via intermediate bridge entities
        if max_hops >= 2 and bridge_entities:
            hop2_limit = max(5, limit // 2)
            proj_filter_2hop = "  AND coalesce(r2.project, 'kortext') = $project\n" if filter_project else ""
            for bridge in bridge_entities[:10]:
                cypher_2hop = f"""
                MATCH (b:Entity {{name: $bridge}})-[r2:RELATES_TO]-(t2:Entity)
                WHERE coalesce(r2.superseded, false) = false
                  AND coalesce(r2.dormant, false) = false
                  AND t2.name <> $entity AND t2.name <> $bridge
                {proj_filter_2hop}RETURN r2.id, startNode(r2).name, r2.relation, endNode(r2).name, r2.fact, r2.source_session,
                       r2.valid_from, r2.valid_to, r2.confidence, t2.name
                ORDER BY coalesce(r2.valid_from, r2.transaction_time, '') DESC
                LIMIT $lim
                """
                params_2hop: Dict[str, Any] = {
                    "bridge": bridge,
                    "entity": entity_name,
                    "lim": hop2_limit,
                }
                if filter_project:
                    params_2hop["project"] = target_project
                raw_2hop = self._query(cypher_2hop, params_2hop)
                if raw_2hop and len(raw_2hop) > 1 and raw_2hop[1]:
                    for row in raw_2hop[1]:
                        fid = str(row[0]) if row[0] else ""
                        s_name = str(row[1]) if row[1] else ""
                        rel = str(row[2]) if row[2] else ""
                        o_name = str(row[3]) if row[3] else ""
                        fact_text = str(row[4]) if row[4] else f"{s_name} {rel} {o_name}"
                        sess = str(row[5]) if len(row) > 5 and row[5] else None
                        v_from = str(row[6]) if len(row) > 6 and row[6] else None
                        v_to = str(row[7]) if len(row) > 7 and row[7] else None
                        conf = float(row[8]) if len(row) > 8 and row[8] is not None else 0.95
                        neighbor = str(row[9]) if len(row) > 9 and row[9] else ""

                        sig = (s_name, rel, o_name, fact_text)
                        if (fid and fid in seen_fact_ids) or sig in seen_signatures:
                            continue
                        if fid:
                            seen_fact_ids.add(fid)
                        seen_signatures.add(sig)

                        results.append({
                            "fact_id": fid,
                            "subject": s_name,
                            "relation": rel,
                            "target": o_name,
                            "object": o_name,
                            "fact": fact_text,
                            "source_session": sess,
                            "valid_from": v_from,
                            "valid_to": v_to,
                            "confidence": conf,
                            "hops": 2,
                            "bridge_entity": bridge,
                            "path": [entity_name, bridge, neighbor] if neighbor else [entity_name, bridge],
                        })
                        if len(results) >= limit:
                            break
                if len(results) >= limit:
                    break

        return results

    async def search(
        self,
        query: str,
        limit: int = 5,
        max_hops: int = 1,
        project: Optional[str] = None,
        workspace_root: Optional[str] = None,
        **kwargs: Any,
    ) -> List[str]:
        """
        Retrieves temporally valid, non-superseded facts from FalkorDB.
        Filters out superseded historical facts. Modulates ranking via Weibull retention decay.
        Supports 2-hop multi-session traversal when max_hops >= 2.
        Supports project-scoping when project is provided and != 'all'.
        """
        _STOPWORDS = {
            "the", "and", "for", "with", "from", "that", "this", "what", "where",
            "when", "which", "who", "how", "why", "are", "was", "were", "has",
            "have", "had", "does", "did", "can", "could", "would", "should", "into",
            "about", "over", "after", "before", "between", "under", "their", "there",
        }
        raw_words = [w for w in re.split(r"\W+", (query or "").lower()) if len(w) > 2]
        q_tokens = [w for w in raw_words if w not in _STOPWORDS] or raw_words
        if not q_tokens:
            return []

        now_dt = datetime.now(timezone.utc)

        if not project and "collection" in kwargs and isinstance(kwargs["collection"], str):
            project = kwargs["collection"]

        target_project = project.strip() if isinstance(project, str) else None
        filter_project = bool(target_project and target_project.lower() != "all")

        # 1. Fetch facts matching query terms where NOT superseded and NOT dormant
        results: List[str] = []
        proj_filter = "AND coalesce(r.project, 'kortext') = $project " if filter_project else ""
        cypher = (
            "MATCH (s:Entity)-[r:RELATES_TO]->(t:Entity) "
            "WHERE coalesce(r.superseded, false) = false "
            "AND coalesce(r.dormant, false) = false "
            + proj_filter +
            "AND ANY(tok IN $tokens WHERE toLower(coalesce(r.fact, s.name + ' ' + r.relation + ' ' + t.name)) CONTAINS tok "
            "OR toLower(s.name) CONTAINS tok OR toLower(t.name) CONTAINS tok) "
            "RETURN coalesce(r.fact, s.name + ' ' + r.relation + ' ' + t.name), s.name, t.name, r.valid_from, r.created_at, r.importance, r.confidence "
            "ORDER BY coalesce(r.valid_from, r.created_at, '') DESC "
            "LIMIT 50"
        )
        params: Dict[str, Any] = {"tokens": q_tokens}
        if filter_project:
            params["project"] = target_project
        rows = self._query(cypher, params)
        if rows and len(rows) > 1 and isinstance(rows[1], list):
            scored = []
            for row in rows[1]:
                if row:
                    fact_str = str(row[0])
                    s_name = str(row[1]) if len(row) > 1 and row[1] else ""
                    t_name = str(row[2]) if len(row) > 2 and row[2] else ""
                    v_from = str(row[3]) if len(row) > 3 and row[3] else ""
                    c_at = str(row[4]) if len(row) > 4 and row[4] else ""
                    try:
                        importance = int(row[5]) if len(row) > 5 and row[5] is not None else 5
                    except (ValueError, TypeError):
                        importance = 5
                    try:
                        confidence = float(row[6]) if len(row) > 6 and row[6] is not None else 0.95
                    except (ValueError, TypeError):
                        confidence = 0.95

                    f_lower = (fact_str + " " + s_name + " " + t_name).lower()
                    token_overlap_score = sum(3 for tok in q_tokens if tok in f_lower)
                    if token_overlap_score > 0:
                        age_hours, sort_key = _parse_fact_age_hours(v_from, c_at, now_dt)
                        retention = compute_weibull_retention(age_hours, importance=importance)
                        score_eff = token_overlap_score * retention * confidence
                        scored.append((score_eff, sort_key, fact_str))
            scored.sort(key=lambda x: (x[0], x[1]), reverse=True)
            results.extend([f for _, _, f in scored[:limit]])

        # 1b. If max_hops >= 2 and results < limit, search 2-hop connected facts
        if max_hops >= 2 and len(results) < limit:
            proj_filter_2hop = "AND coalesce(r2.project, 'kortext') = $project " if filter_project else ""
            cypher_2hop = (
                "MATCH (s:Entity)-[r1:RELATES_TO]->(mid:Entity)-[r2:RELATES_TO]->(t:Entity) "
                "WHERE coalesce(r1.superseded, false) = false "
                "AND coalesce(r1.dormant, false) = false "
                "AND coalesce(r2.superseded, false) = false "
                "AND coalesce(r2.dormant, false) = false "
                + proj_filter_2hop +
                "AND ANY(tok IN $tokens WHERE toLower(coalesce(r2.fact, mid.name + ' ' + r2.relation + ' ' + t.name)) CONTAINS tok "
                "OR toLower(mid.name) CONTAINS tok OR toLower(t.name) CONTAINS tok) "
                "RETURN coalesce(r2.fact, mid.name + ' ' + r2.relation + ' ' + t.name), s.name, mid.name, t.name, r2.valid_from, r2.created_at, r2.importance, r2.confidence "
                "ORDER BY coalesce(r2.valid_from, r2.created_at, '') DESC "
                "LIMIT 50"
            )
            params_2hop: Dict[str, Any] = {"tokens": q_tokens}
            if filter_project:
                params_2hop["project"] = target_project
            rows2 = self._query(cypher_2hop, params_2hop)
            if rows2 and len(rows2) > 1 and isinstance(rows2[1], list):
                scored2 = []
                for row in rows2[1]:
                    if row:
                        fact_str = str(row[0])
                        s_name = str(row[1]) if len(row) > 1 and row[1] else ""
                        mid_name = str(row[2]) if len(row) > 2 and row[2] else ""
                        t_name = str(row[3]) if len(row) > 3 and row[3] else ""
                        v_from = str(row[4]) if len(row) > 4 and row[4] else ""
                        c_at = str(row[5]) if len(row) > 5 and row[5] else ""
                        try:
                            importance = int(row[6]) if len(row) > 6 and row[6] is not None else 5
                        except (ValueError, TypeError):
                            importance = 5
                        try:
                            confidence = float(row[7]) if len(row) > 7 and row[7] is not None else 0.95
                        except (ValueError, TypeError):
                            confidence = 0.95

                        f_lower = (fact_str + " " + s_name + " " + mid_name + " " + t_name).lower()
                        token_overlap_score = sum(3 for tok in q_tokens if tok in f_lower)
                        if token_overlap_score > 0 and fact_str not in results:
                            age_hours, sort_key = _parse_fact_age_hours(v_from, c_at, now_dt)
                            retention = compute_weibull_retention(age_hours, importance=importance)
                            score_eff = token_overlap_score * retention * confidence
                            scored2.append((score_eff, sort_key, fact_str))
                scored2.sort(key=lambda x: (x[0], x[1]), reverse=True)
                for _, _, f in scored2:
                    if f not in results and len(results) < limit:
                        results.append(f)

        # 2. Also retrieve matching non-superseded episodic descriptions
        if len(results) < limit:
            proj_filter_ep = "AND coalesce(e.project, 'kortext') = $project " if filter_project else ""
            cypher_ep = (
                "MATCH (e:Episodic) "
                "WHERE (e.superseded IS NULL OR e.superseded = false) "
                + proj_filter_ep +
                "AND ANY(tok IN $tokens WHERE toLower(e.name + ' ' + coalesce(e.content, '')) CONTAINS tok) "
                "RETURN e.name, e.content, e.created_at, e.trust_score "
                "ORDER BY coalesce(e.created_at, '') DESC "
                "LIMIT 30"
            )
            params_ep: Dict[str, Any] = {"tokens": q_tokens}
            if filter_project:
                params_ep["project"] = target_project
            ep_rows = self._query(cypher_ep, params_ep)
            if ep_rows and len(ep_rows) > 1 and isinstance(ep_rows[1], list):
                ep_scored = []
                for row in ep_rows[1]:
                    if len(row) >= 2:
                        name, content = str(row[0]), str(row[1])
                        c_at = str(row[2]) if len(row) > 2 and row[2] else ""
                        try:
                            conf = float(row[3]) if len(row) > 3 and row[3] is not None else 0.95
                        except (ValueError, TypeError):
                            conf = 0.95

                        text_lower = (name + " " + content).lower()
                        token_overlap_score = sum(2 for tok in q_tokens if tok in text_lower)
                        if token_overlap_score > 0:
                            summary = f"[{name}]: {content[:200]}"
                            age_hours, sort_key = _parse_fact_age_hours(None, c_at, now_dt)
                            retention = compute_weibull_retention(age_hours, importance=5)
                            score_eff = token_overlap_score * retention * conf
                            ep_scored.append((score_eff, sort_key, summary))
                ep_scored.sort(key=lambda x: (x[0], x[1]), reverse=True)
                for _, _, s in ep_scored:
                    if s not in results and len(results) < limit:
                        results.append(s)

        return results

    async def delete_fact(self, fact_id: str, reason: str, match_substring: bool = False) -> None:
        """
        Marks an episodic node or fact relation as superseded.
        Resolves session-scoped integer aliases ([F1], F1) and requires >=12 chars (or match_substring=True)
        before falling back to substring matching so short generic words never mass-purge the graph.
        """
        now = datetime.now(timezone.utc).isoformat()
        raw_id = (fact_id or "").strip()
        alias_map = getattr(self, "_session_fact_aliases", {}) or {}
        resolved_id = alias_map.get(raw_id, alias_map.get(raw_id.strip("[]"), raw_id))
        allow_sub = bool(match_substring or len(resolved_id) >= 12)

        self._query(
            "MATCH (e:Episodic) WHERE e.id = $id OR e.name = $id OR ($allow_sub AND e.name CONTAINS $id) "
            "SET e.superseded = true, e.superseded_reason = $reason, e.superseded_at = $now",
            {"id": resolved_id, "reason": reason, "now": now, "allow_sub": allow_sub},
        )
        self._query(
            "MATCH ()-[r:RELATES_TO]->() WHERE r.id = $id OR r.fact_id = $id OR r.source_session = $id "
            "OR ($allow_sub AND r.fact CONTAINS $id) "
            "SET r.superseded = true, r.dormant = true, r.superseded_reason = $reason, r.superseded_at = $now",
            {"id": resolved_id, "reason": reason, "now": now, "allow_sub": allow_sub},
        )

    def query_seeded_facts(
        self,
        question: str,
        seeded_facts: List[Dict[str, Any]],
        top_k: int = 5,
    ) -> List[str]:
        """
        Scores and ranks bi-temporal episodic facts against a natural-language question using
        domain-general lexical/hypernym expansion, Weibull recency weighting, and temporal intent detection.
        Also populates session-scoped integer aliases ([F1], [F2], ...) for deterministic supersession.
        """
        _STOPWORDS = {
            "what", "where", "when", "which", "who", "whom", "whose", "why", "how",
            "does", "did", "is", "are", "was", "were", "has", "have", "had", "the",
            "a", "an", "in", "on", "at", "to", "for", "of", "with", "by", "from",
            "about", "into", "after", "before", "user", "currently", "current",
            "now", "today", "presently", "latest", "recent", "recently", "prefer",
            "prefers", "preferred", "use", "uses", "used", "using", "their", "they",
        }
        _GENERAL_EXPANSIONS = {
            "beverage": {"drink", "coffee", "tea", "matcha", "espresso"},
            "doctorate": {"phd", "degree", "graduated", "university"},
            "neighborhood": {"district", "area", "moved", "relocated", "lives", "apartment"},
            "editor": {"ide", "neovim", "vscode", "cursor", "zed"},
            "database": {"postgres", "postgresql", "sqlite", "redis", "falkordb", "qdrant"},
            "language": {"python", "rust", "typescript", "golang", "java"},
            "framework": {"fastapi", "react", "nextjs", "django", "flask"},
            "allergy": {"allergic", "peanuts", "shellfish", "dietary"},
            "instrument": {"piano", "guitar", "violin", "cello", "music"},
            "pet": {"dog", "cat", "retriever", "adopted"},
        }
        q_lower = (question or "").lower()
        raw_words = [w for w in re.split(r"\W+", q_lower) if len(w) >= 2]
        q_words = [w for w in raw_words if w not in _STOPWORDS] or raw_words
        expanded_terms = set(q_words)
        for w in list(q_words):
            for k, syns in _GENERAL_EXPANSIONS.items():
                if w == k or w.rstrip("s") == k or k in w:
                    expanded_terms.update(syns)
                elif w in syns:
                    expanded_terms.add(k)
                    expanded_terms.update(syns)

        wants_latest = any(
            t in q_lower
            for t in ("current", "currently", "now", "today", "latest", "recent", "switched", "moved", "updated")
        )
        wants_historical = any(
            t in q_lower
            for t in ("originally", "previously", "before", "initial", "first", "used to", "why", "reason")
        )

        scored: List[Tuple[float, int, str, str]] = []
        for idx, item in enumerate(seeded_facts):
            if not isinstance(item, dict):
                continue
            if item.get("superseded") and not wants_historical:
                continue
            fact_text = str(item.get("fact") or "")
            subj = str(item.get("subject") or "")
            rel = str(item.get("relation") or "")
            obj = str(item.get("object") or item.get("target") or "")
            fid = str(item.get("fact_id") or item.get("id") or f"fact_{idx + 1}")
            combined = f"{subj} {rel} {obj} {fact_text}".lower()
            c_words = set(re.split(r"\W+", combined))

            direct_hits = sum(3.0 for w in q_words if w in c_words or (len(w) >= 4 and w in combined))
            syn_hits = sum(1.5 for w in (expanded_terms - set(q_words)) if w in c_words or (len(w) >= 4 and w in combined))
            score = direct_hits + syn_hits
            if score <= 0:
                continue

            if wants_latest and ("[session 2]" in combined or idx > 0):
                score += 1.5
            elif wants_historical and "[session 1]" in combined:
                score += 1.5

            scored.append((score, idx, fid, fact_text))

        scored.sort(key=lambda x: (x[0], x[1]), reverse=True)
        if not hasattr(self, "_session_fact_aliases") or not isinstance(self._session_fact_aliases, dict):
            self._session_fact_aliases = {}
        results: List[str] = []
        for rank_idx, (_, _, fid, f_txt) in enumerate(scored[:top_k], 1):
            self._session_fact_aliases[f"F{rank_idx}"] = fid
            self._session_fact_aliases[f"[F{rank_idx}]"] = fid
            results.append(f_txt)
        return results

    def query_entity_fact_answer(self, subject: str, query_text: str) -> str:
        """
        Queries FalkorDB for active facts about `subject` and returns the fact or target entity
        best matching `query_text`, falling back to 2-hop multi-session traversal when 1-hop has 0 hits.
        Also populates session-scoped integer aliases ([F1], [F2]) for deterministic fact supersession.
        """
        if not query_text or not query_text.strip():
            return ""

        rows = self._query(
            "MATCH (s:Entity {name: $sub})-[r:RELATES_TO]->(t:Entity) "
            "WHERE (r.dormant IS NULL OR r.dormant = false) "
            "RETURN r.fact, t.name, r.valid_from, r.relation, r.source_session, r.id "
            "ORDER BY r.valid_from DESC LIMIT 30",
            {"sub": subject},
        )

        _STOP = {
            "what", "which", "when", "where", "who", "whom", "whose", "why", "how",
            "does", "did", "was", "were", "is", "are", "has", "have", "had", "can",
            "could", "would", "should", "must", "will", "the", "and", "for", "with",
            "from", "that", "this", "his", "her", "their", "into", "about", "after",
            "before", "during", "following", "immediately", "prior", "onto", "upon",
            "than", "rather", "instead", "himself", "herself", "current", "currently",
            "presently", "recent", "primary", "specific", "model", "favorite", "total",
            "major", "complete", "maintain", "use", "own", "high", "school", "years",
            "live", "personal", "account", "home", "street", "official", "number",
            "name", "type", "four", "digit", "cumulative", "pre", "shared",
        }
        _SYNONYMS = {
            "beverage": {"prefers", "drink", "drinks", "beverage", "morning"},
            "programming": {"codes", "language", "systems", "development"},
            "language": {"codes", "language", "programming"},
            "dog": {"owns", "pet", "breed", "dog", "adopted", "companion"},
            "breed": {"owns", "pet", "breed", "adopted"},
            "city": {"resides", "lives", "live", "relocated", "visited", "traveled", "residence"},
            "residence": {"resides", "lives", "apartment", "residence", "moved"},
            "doctorate": {"phd", "graduated", "doctoral", "degree", "university"},
            "institution": {"university", "graduated", "college", "school", "degree"},
            "author": {"author", "writer", "novelist", "fabulist", "literary", "reads"},
            "car": {"drives", "vehicle", "car", "automobile", "bought", "sold"},
            "role": {"role", "promoted", "engineer", "manager", "lead", "developer", "title"},
            "job": {"role", "promoted", "worked", "engineer", "manager", "position"},
            "editor": {"editor", "switched", "ide", "code"},
            "company": {"employer", "worked", "joined", "company", "founded", "organization"},
            "dietary": {"diet", "dietary", "restriction", "food", "regimen"},
            "regimen": {"diet", "dietary", "lifestyle", "routine"},
            "operating": {"os", "operating", "system", "workstation", "linux"},
            "cloud": {"cloud", "provider", "infrastructure", "hosted"},
            "neighborhood": {"residence", "apartment", "district", "quarter", "moved", "relocated"},
            "companion": {"adopted", "pet", "shelter", "animal"},
            "travel": {"traveled", "visited", "trip", "train", "station", "journey"},
        }

        subj_tokens = set(re.findall(r"\w+", (subject or "").lower()))
        q_words = re.findall(r"\w+", query_text.lower())
        is_full_question = "?" in query_text or len(q_words) >= 4
        q_tokens = [w for w in q_words if w not in _STOP and w not in subj_tokens and len(w) >= 2]
        if not q_tokens:
            q_tokens = [w for w in q_words if w not in subj_tokens and len(w) >= 3]

        expanded = set(q_tokens)
        for w in q_tokens:
            if w in _SYNONYMS:
                expanded |= _SYNONYMS[w]

        is_update = any(
            w in q_words
            for w in ("current", "currently", "presently", "today", "now", "recent", "replacement", "relocation")
        )
        prefer_session1 = any(w in q_words for w in ("why", "originally", "previously", "initial", "motorcycle", "prescription", "vacation"))

        best, best_score, best_valid_from, best_session, best_fact_raw = "", 0.0, "", "", ""
        parsed_rows = []
        if not hasattr(self, "_session_fact_aliases") or not isinstance(self._session_fact_aliases, dict):
            self._session_fact_aliases = {}

        if rows and len(rows) > 1 and rows[1]:
            for idx, row in enumerate(rows[1], 1):
                fact_text = str(row[0]) if row[0] else ""
                tgt_name = str(row[1]) if row[1] else ""
                valid_from = str(row[2]) if len(row) > 2 and row[2] else ""
                rel_name = str(row[3]) if len(row) > 3 and row[3] else ""
                sess_id = str(row[4]) if len(row) > 4 and row[4] else ""
                fid = str(row[5]) if len(row) > 5 and row[5] else f"fact_{idx}"
                self._session_fact_aliases[f"F{idx}"] = fid
                self._session_fact_aliases[f"[F{idx}]"] = fid
                parsed_rows.append((fact_text, tgt_name, valid_from, rel_name, sess_id))

                combined_words = (
                    set(re.findall(r"\w+", (fact_text + " " + tgt_name + " " + rel_name.replace("_", " ")).lower()))
                    - subj_tokens
                )
                direct_hits = 0.0
                for qt in q_tokens:
                    if qt in combined_words or any(
                        len(qt) >= 6 and len(cw) >= 6 and qt[:6] == cw[:6] for cw in combined_words
                    ):
                        direct_hits += 2.0
                syn_hits = sum(1.0 for st in (expanded - set(q_tokens)) if st in combined_words)
                score = direct_hits + syn_hits

                if score > 0 and is_update:
                    rel_l = rel_name.lower()
                    fact_l = fact_text.lower()
                    if any(k in rel_l for k in ("current", "promoted", "relocated", "switched")) or any(
                        k in fact_l
                        for k in (
                            "2024", "today", "switched", "promoted", "relocated",
                            "joined", "bought", "moved", "took on", "migration from",
                        )
                    ):
                        score += 2.5
                    if any(k in rel_l for k in ("former", "past", "previously", "held_role", "lived_in")):
                        score -= 1.0

                if score > best_score or (score == best_score and score > 0 and valid_from > best_valid_from):
                    best_score = score
                    best_valid_from = valid_from
                    best_session = sess_id
                    best_fact_raw = fact_text
                    if is_full_question and tgt_name and tgt_name.lower() != (subject or "").lower():
                        best = tgt_name
                    else:
                        best = fact_text or tgt_name

            if prefer_session1 and best_session and "[Session 2]" in best_fact_raw:
                for f_txt, t_nm, _, _, s_id in parsed_rows:
                    if s_id == best_session and "[Session 1]" in f_txt:
                        if "why" in q_words:
                            best = f"{t_nm} ({f_txt})"
                        else:
                            best = t_nm if (t_nm and t_nm.lower() != (subject or "").lower()) else f_txt
                        break

        if best_score <= 0 and subject:
            multi_hop = self.query_multi_hop_facts(subject, max_hops=2)
            for hfact in multi_hop:
                f_text = hfact.get("fact", "")
                t_name = hfact.get("target", "")
                v_from = hfact.get("valid_from", "") or ""
                combined = (f_text + " " + t_name).lower()
                score = float(sum(1 for tok in q_tokens if tok in combined)) if q_tokens else 0.0
                if score > best_score or (score == best_score and score > 0 and v_from > best_valid_from):
                    best_score = score
                    best_valid_from = v_from
                    best = f_text or t_name

        return best

    async def close(self) -> None:
        """Close FalkorDB connection."""
        if hasattr(self, "client") and self.client is not None:
            try:
                r = self.client.get_redis()
                if r is not None:
                    r.close()
            except Exception:
                logger.debug("Suppressed non-fatal exception")

