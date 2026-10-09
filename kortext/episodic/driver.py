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

FALKORDB_DB   = os.getenv("KORTEXT_DATABASE", os.getenv("FALKORDB_DATABASE", "kortext"))


TRUST_ANCHOR_LEVELS: Dict[str, float] = {
    "speculative": 0.50,
    "tool_confirmed": 0.60,
    "user_approved": 1.00,
}


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

    def _get_client(self) -> redis.Redis:
        return self.client.get_redis()

    def _query(self, cypher: str, params: Optional[Dict[str, Any]] = None) -> List[List[Any]]:
        return self.client.query(self.db_name, cypher, params)

    async def record_outcome(
        self,
        episode_name: str,
        content: str,
        tags: Optional[List[str]] = None,
        project: Optional[str] = None,
        entities: Optional[List[Dict[str, str]]] = None,
        facts: Optional[List[Dict[str, str]]] = None,
        supersedes: Optional[List[str]] = None,
        trust_level: str = "speculative",
    ) -> Dict[str, Any]:
        """
        Agent-Native recording with Trust Anchor State Machine:
          - speculative (0.50): unverified hypothesis or initial code draft
          - tool_confirmed (0.60): validated by test execution, linter, or compiler
          - user_approved (1.00): explicitly sanctioned by the user
        Inserts (:Episodic), (:Entity), and [:RELATES_TO] edges directly into FalkorDB.
        Exposure does not validate: reading facts never promotes or mutates trust levels.
        """
        now = datetime.now(timezone.utc).isoformat()
        proj = project or "kortext"

        norm_level = trust_level.lower().strip() if isinstance(trust_level, str) else "speculative"
        trust_score = TRUST_ANCHOR_LEVELS.get(norm_level, 0.50)

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
                        pass

        # 2. Persist (:Episodic) Node with Trust Anchor
        tags_str = ", ".join(tags) if tags else ""
        self._query(
            "MERGE (e:Episodic {name: $name}) "
            "SET e.content = $content, e.created_at = $now, e.project = $project, "
            "e.tags = $tags, e.superseded = false, e.trust_level = $trust_level, "
            "e.trust_score = $trust_score",
            {
                "name": episode_name,
                "content": content,
                "now": now,
                "project": proj,
                "tags": tags_str,
                "trust_level": norm_level,
                "trust_score": trust_score,
            },
        )

        # 3. Handle Entities & Facts (provided directly by calling agent)
        actual_entities = entities or []
        actual_facts = facts or []

        # Sanitize facts against MINJA prompt injections
        source_tier = 1 if norm_level == "user_approved" else (2 if norm_level == "tool_confirmed" else 3)
        valid_facts = []
        for f in actual_facts:
            src = f.get("source", "").strip()
            tgt = f.get("target", "").strip()
            rel = (f.get("relation") or "RELATES_TO").upper().replace(" ", "_")
            fact_text = f.get("fact") or f"{src} {rel} {tgt}"
            try:
                self.sanitizer.sanitize(subject=src, relation=rel, fact=fact_text, source_tier=source_tier)
                valid_facts.append(f)
            except SecurityViolation:
                pass
        actual_facts = valid_facts

        # Write Entities
        for ent in actual_entities:
            ename = ent.get("name", "").strip()
            if not ename:
                continue
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
            src = f.get("source", "").strip()
            tgt = f.get("target", "").strip()
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
                    "r.trust_level = $trust_level, r.trust_score = $trust_score",
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
                    },
                )

        return {
            "status": "ok",
            "episode": episode_name,
            "trust_level": norm_level,
            "trust_score": trust_score,
            "entities_written": len(actual_entities),
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
    ) -> str:
        """
        Records an episodic relationship between subject and object entities with bi-temporal attribution.
        Automatically resolves conflicting facts by materializing [:SUPERSEDES] edges (Section 53, Invariant D5, D30).
        """
        # Sanitize untrusted fact text against MINJA prompt injections before persisting
        self.sanitizer.sanitize(subject=subject, relation=relation, fact=fact, source_tier=source_tier)

        fact_id = f"fact_{uuid.uuid4().hex[:10]}"
        now = datetime.now(timezone.utc).isoformat()
        v_start = valid_from or now
        obj = (object_name or relation).strip()

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
            valid_from: $v_start,
            valid_to: $v_end,
            created_at: $now,
            transaction_time: $now,
            importance: $imp,
            confidence: $conf,
            source_session: $session,
            dormant: false,
            superseded: false
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
    ) -> List[Dict[str, Any]]:
        """
        Executes a point-in-time bi-temporal query returning facts valid on a specific date (Invariant D5).
        """
        cypher = """
        MATCH (s:Entity {name: $sub})-[r:RELATES_TO]->(target)
        WHERE r.valid_from <= $target_date
          AND (r.valid_to IS NULL OR r.valid_to > $target_date)
        RETURN r.id, s.name, r.relation, r.fact, r.valid_from, r.valid_to, r.confidence
        ORDER BY r.valid_from DESC
        LIMIT $lim
        """
        raw = self._query(cypher, {
            "sub": subject,
            "target_date": as_of_date,
            "lim": limit,
        })

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
    ) -> List[Dict[str, Any]]:
        """
        Traverses episodic memory up to max_hops (default 2) starting from entity_name.
        Discovers connected facts across different sessions via intermediate bridge entities.
        Filters out dormant and superseded relationships.
        """
        if not entity_name or max_hops < 1:
            return []

        # 1. Fetch 1-hop facts connected to entity_name (both outgoing and incoming)
        cypher_1hop = """
        MATCH (s:Entity {name: $entity})-[r:RELATES_TO]-(t:Entity)
        WHERE coalesce(r.superseded, false) = false
          AND coalesce(r.dormant, false) = false
        RETURN r.id, startNode(r).name, r.relation, endNode(r).name, r.fact, r.source_session,
               r.valid_from, r.valid_to, r.confidence, t.name
        ORDER BY coalesce(r.valid_from, r.transaction_time, '') DESC
        LIMIT $lim
        """
        raw_1hop = self._query(cypher_1hop, {"entity": entity_name, "lim": limit})

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
            for bridge in bridge_entities[:10]:
                cypher_2hop = """
                MATCH (b:Entity {name: $bridge})-[r2:RELATES_TO]-(t2:Entity)
                WHERE coalesce(r2.superseded, false) = false
                  AND coalesce(r2.dormant, false) = false
                  AND t2.name <> $entity AND t2.name <> $bridge
                RETURN r2.id, startNode(r2).name, r2.relation, endNode(r2).name, r2.fact, r2.source_session,
                       r2.valid_from, r2.valid_to, r2.confidence, t2.name
                ORDER BY coalesce(r2.valid_from, r2.transaction_time, '') DESC
                LIMIT $lim
                """
                raw_2hop = self._query(cypher_2hop, {
                    "bridge": bridge,
                    "entity": entity_name,
                    "lim": hop2_limit,
                })
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

    async def search(self, query: str, limit: int = 5, max_hops: int = 1) -> List[str]:
        """
        Retrieves temporally valid, non-superseded facts from FalkorDB.
        Filters out superseded historical facts. Modulates ranking via Weibull retention decay.
        Supports 2-hop multi-session traversal when max_hops >= 2.
        """
        q_tokens = [w.lower() for w in query.split() if len(w) > 2]
        if not q_tokens:
            return []

        now_dt = datetime.now(timezone.utc)

        # 1. Fetch facts matching query terms where NOT superseded and NOT dormant
        results: List[str] = []
        cypher = (
            "MATCH (s:Entity)-[r:RELATES_TO]->(t:Entity) "
            "WHERE coalesce(r.superseded, false) = false "
            "AND coalesce(r.dormant, false) = false "
            "AND ANY(tok IN $tokens WHERE toLower(coalesce(r.fact, s.name + ' ' + r.relation + ' ' + t.name)) CONTAINS tok "
            "OR toLower(s.name) CONTAINS tok OR toLower(t.name) CONTAINS tok) "
            "RETURN coalesce(r.fact, s.name + ' ' + r.relation + ' ' + t.name), s.name, t.name, r.valid_from, r.created_at, r.importance, r.confidence "
            "ORDER BY coalesce(r.valid_from, r.created_at, '') DESC "
            "LIMIT 50"
        )
        rows = self._query(cypher, {"tokens": q_tokens})
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
            cypher_2hop = (
                "MATCH (s:Entity)-[r1:RELATES_TO]->(mid:Entity)-[r2:RELATES_TO]->(t:Entity) "
                "WHERE coalesce(r1.superseded, false) = false "
                "AND coalesce(r1.dormant, false) = false "
                "AND coalesce(r2.superseded, false) = false "
                "AND coalesce(r2.dormant, false) = false "
                "AND ANY(tok IN $tokens WHERE toLower(coalesce(r2.fact, mid.name + ' ' + r2.relation + ' ' + t.name)) CONTAINS tok "
                "OR toLower(mid.name) CONTAINS tok OR toLower(t.name) CONTAINS tok) "
                "RETURN coalesce(r2.fact, mid.name + ' ' + r2.relation + ' ' + t.name), s.name, mid.name, t.name, r2.valid_from, r2.created_at, r2.importance, r2.confidence "
                "ORDER BY coalesce(r2.valid_from, r2.created_at, '') DESC "
                "LIMIT 50"
            )
            rows2 = self._query(cypher_2hop, {"tokens": q_tokens})
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
            cypher_ep = (
                "MATCH (e:Episodic) "
                "WHERE (e.superseded IS NULL OR e.superseded = false) "
                "AND ANY(tok IN $tokens WHERE toLower(e.name + ' ' + coalesce(e.content, '')) CONTAINS tok) "
                "RETURN e.name, e.content, e.created_at, e.trust_score "
                "ORDER BY coalesce(e.created_at, '') DESC "
                "LIMIT 30"
            )
            ep_rows = self._query(cypher_ep, {"tokens": q_tokens})
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

    async def delete_fact(self, fact_id: str, reason: str) -> None:
        """Marks an episodic node or fact relation as superseded."""
        now = datetime.now(timezone.utc).isoformat()
        self._query(
            "MATCH (e:Episodic) WHERE e.id = $id OR e.name = $id OR e.name CONTAINS $id "
            "SET e.superseded = true, e.superseded_reason = $reason, e.superseded_at = $now",
            {"id": fact_id, "reason": reason, "now": now},
        )
        self._query(
            "MATCH ()-[r:RELATES_TO]->() WHERE r.id = $id OR r.fact_id = $id OR r.fact CONTAINS $id "
            "SET r.superseded = true, r.dormant = true, r.superseded_reason = $reason, r.superseded_at = $now",
            {"id": fact_id, "reason": reason, "now": now},
        )

    async def close(self) -> None:
        """Close FalkorDB connection."""
        if hasattr(self, "client") and self.client is not None:
            try:
                r = self.client.get_redis()
                if r is not None:
                    r.close()
            except Exception:
                pass

