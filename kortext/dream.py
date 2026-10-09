"""
Dream mode: offline memory reflection, synaptic pruning, and subsystem synthesis.

100% Agent-Native:
- Contradiction auditing and invariant induction are driven directly by the frontier Antigravity agent.
- Zero local LLM chat completion dependencies on :8000 (reserving Metal GPU for embeddings & reranking).
- Louvain Subsystem Community Detection is fully deterministic and runs in <5ms.
- Synaptic pruning archives superseded FalkorDB nodes into markdown and purges them.

Can be triggered on-demand via:
1. CLI: python -m kortext.dream [--project kortext] [--purge-stale] [--dry-run]
2. Antigravity Agent MCP Tool: trigger_dream_mode(project, purge_stale, dry_run, invariants, stale_fact_names)
3. Kortext Dashboard: 'Trigger Dream Mode' button on http://localhost:8004
"""
from __future__ import annotations

import argparse
import asyncio
import json
import logging
import os
import re
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional
import warnings
import redis

import math
from kortext.symbols.clustering import SubsystemClusterer
from kortext.falkordb_client import (
    FalkorDBClient,
    FALKORDB_HOST,
    FALKORDB_PORT,
    FALKORDB_PASS,
    get_shared_falkordb_client,
)
from kortext.invariants import InvariantGroundingEngine

logger = logging.getLogger(__name__)

FALKORDB_DB   = os.getenv("KORTEXT_DATABASE", os.getenv("FALKORDB_DATABASE", "kortext"))
DEFAULT_SYMBOLS_DB = os.getenv("KORTEXT_SYMBOLS_GRAPH", os.getenv("FALKORDB_SYMBOLS_GRAPH", "kortext_symbols"))

KORTEXT_ROOT   = Path(__file__).resolve().parent.parent
CEREBRUM_ROOT   = KORTEXT_ROOT
JOURNAL_DIR   = Path(os.getenv("JOURNAL_DIR", str(KORTEXT_ROOT / "journal")))
ARCHIVE_DIR   = JOURNAL_DIR / "archive"
DREAMS_DIR    = JOURNAL_DIR / "dreams"
REPORTS_DIR   = JOURNAL_DIR / "reports"
INVARIANTS_FILE = JOURNAL_DIR / "invariants.md"


class DreamEngine:
    """The cognitive consolidation and reflection engine for Kortext (Agent-Native)."""

    def __init__(
        self,
        host: str = FALKORDB_HOST,
        port: int = FALKORDB_PORT,
        password: Optional[str] = FALKORDB_PASS,
        episodic_db: str = FALKORDB_DB,
        symbols_db: str = DEFAULT_SYMBOLS_DB,
        half_life_hours: float = 72.0,
        shape_parameter: float = 0.65,
        biological_floor: float = 0.05,
        client: Optional[FalkorDBClient] = None,
    ):
        self.host = host
        self.port = port
        self.password = password or None
        self.episodic_db = episodic_db
        self.symbols_db = symbols_db
        self.half_life_hours = half_life_hours
        self.shape_parameter = shape_parameter
        self.biological_floor = biological_floor
        self.client = client if client is not None else get_shared_falkordb_client(host=self.host, port=self.port, password=self.password)
        self.invariant_engine = InvariantGroundingEngine(
            host=self.host,
            port=self.port,
            password=self.password,
            db_name=self.episodic_db,
            client=self.client,
        )

        ARCHIVE_DIR.mkdir(parents=True, exist_ok=True)
        DREAMS_DIR.mkdir(parents=True, exist_ok=True)
        REPORTS_DIR.mkdir(parents=True, exist_ok=True)

    def _get_client(self) -> redis.Redis:
        return self.client.get_redis()

    def _query(self, db_name: str, cypher: str, params: Optional[Dict[str, Any]] = None) -> List[List[Any]]:
        return self.client.query(db_name, cypher, params)

    def compute_retention(self, elapsed_hours: float, importance: float = 5.0) -> float:
        """
        Computes effective retention using the Stretched Weibull Decay Model:
        R(t) = exp(-(t / (lambda * exp(S / 10)))^beta)
        Subject to biological retention floor R_min = 0.05.
        """
        s_factor = math.exp(float(importance) / 10.0)
        scale = self.half_life_hours * s_factor
        t = max(float(elapsed_hours), 0.0)
        retention = math.exp(-((t / scale) ** self.shape_parameter))
        return max(retention, self.biological_floor)

    def sweep_weibull_decay(self, dry_run: bool = False) -> int:
        """
        Sweeps all episodic facts, evaluates Weibull retention decay,
        and marks facts below floor as dormant.
        """
        cypher = """
        MATCH ()-[r:RELATES_TO]->()
        WHERE r.dormant IS NULL OR r.dormant = false
        RETURN id(r) AS rel_id, r.created_at AS created_at, r.importance AS importance
        """
        raw = self._query(self.episodic_db, cypher)
        if not raw or len(raw) < 2 or not raw[1]:
            return 0

        now = datetime.now(timezone.utc)
        dormant_ids = []

        for row in raw[1]:
            rel_id = row[0]
            created_at_str = row[1]
            importance = float(row[2] or 5.0)
            try:
                dt = datetime.fromisoformat(created_at_str)
                if dt.tzinfo is None:
                    dt = dt.replace(tzinfo=timezone.utc)
                delta_hours = max((now - dt).total_seconds() / 3600.0, 0.0)
                r_eff = self.compute_retention(delta_hours, importance)
                if r_eff <= self.biological_floor:
                    dormant_ids.append(rel_id)
            except Exception:
                continue

        if dormant_ids and not dry_run:
            dormant_cypher = """
            UNWIND $ids AS target_id
            MATCH ()-[r:RELATES_TO]->() WHERE id(r) = target_id
            SET r.dormant = true
            """
            self._query(self.episodic_db, dormant_cypher, {"ids": dormant_ids})

        return len(dormant_ids)

    # ── Phase 1: Synaptic Pruning & Stale Fact Cleanup ─────────────────────────

    async def prune_stale_facts(
        self,
        purge_stale: bool = True,
        dry_run: bool = False,
        stale_fact_names: Optional[List[str]] = None,
    ) -> Dict[str, Any]:
        """
        Audits episodic memory for outdated, superseded, or contradictory facts.
        Operates deterministically on FalkorDB `superseded = true` facts or agent-supplied facts.
        """
        now = datetime.now(timezone.utc).isoformat()
        today_str = datetime.now().strftime("%Y-%m-%d")

        superseded_details: List[Dict[str, str]] = []

        # 1. If explicit stale facts were supplied by the agent, mark them superseded
        if stale_fact_names:
            for s_name in stale_fact_names:
                superseded_details.append({
                    "stale_name": s_name,
                    "superseded_by": "Agent Reflection",
                    "reason": "Superseded during cognitive consolidation",
                })
                if not dry_run:
                    self._query(
                        self.episodic_db,
                        "MATCH (e:Episodic) WHERE e.name = $name "
                        "SET e.superseded = true, e.superseded_by = 'Agent Reflection', "
                        "e.superseded_at = $now, e.superseded_reason = 'Superseded during cognitive consolidation'",
                        {"name": s_name, "now": now},
                    )

        # 2. Find all superseded facts in FalkorDB
        archived_entries: List[str] = []
        superseded_rows = self._query(
            self.episodic_db,
            "MATCH (e:Episodic) WHERE e.superseded = true "
            "RETURN e.name, e.content, e.created_at, e.superseded_by, e.superseded_reason",
        )
        if superseded_rows and len(superseded_rows) > 1 and isinstance(superseded_rows[1], list):
            for r in superseded_rows[1]:
                if len(r) >= 3:
                    s_name = str(r[0])
                    s_content = str(r[1] or "")
                    s_created = str(r[2] or "")
                    s_by = str(r[3] or "Newer configuration") if len(r) > 3 and r[3] else "Newer configuration"
                    s_reason = str(r[4] or "Outdated operational state") if len(r) > 4 and r[4] else "Outdated operational state"

                    if not any(d["stale_name"] == s_name for d in superseded_details):
                        superseded_details.append({
                            "stale_name": s_name,
                            "superseded_by": s_by,
                            "reason": s_reason,
                        })

                    if purge_stale and not dry_run:
                        archived_entries.append(
                            f"### {s_name} (Created: {s_created})\n"
                            f"**Superseded By:** {s_by}\n"
                            f"**Reason:** {s_reason}\n\n"
                            f"{s_content}\n\n---\n"
                        )
                        self._query(
                            self.episodic_db,
                            "MATCH (e:Episodic {name: $name}) DETACH DELETE e",
                            {"name": s_name},
                        )

        if archived_entries and not dry_run:
            archive_file = ARCHIVE_DIR / f"{today_str}-archived.md"
            with open(archive_file, "a", encoding="utf-8") as f:
                f.write("\n\n" + "\n".join(archived_entries))

        # Query active count
        active_count = 0
        active_rows = self._query(
            self.episodic_db,
            "MATCH (e:Episodic) WHERE (e.superseded IS NULL OR e.superseded = false) RETURN count(e)",
        )
        if active_rows and len(active_rows) > 1 and isinstance(active_rows[1], list) and active_rows[1]:
            try:
                active_count = int(active_rows[1][0][0])
            except Exception:
                pass

        return {
            "superseded_count": len(superseded_details),
            "archived_count": len(archived_entries),
            "active_count": active_count,
            "contradictions": [d["stale_name"] for d in superseded_details],
            "details": superseded_details,
        }

    # ── Phase 2: Louvain Subsystem Community Detection ────────────────────────

    async def cluster_subsystems(self, persist: bool = True) -> List[Dict[str, Any]]:
        """Executes Louvain Community Detection and synthesizes :Subsystem nodes."""
        clusterer = SubsystemClusterer(
            host=self.host,
            port=self.port,
            password=self.password,
            graph_name=self.symbols_db,
        )
        return await clusterer.detect_subsystems(persist=persist)

    # ── Phase 3: Abstract Invariant Induction & AST Grounding ──────────────

    async def induce_invariants(
        self,
        invariants: Optional[List[Dict[str, str]]] = None,
        dry_run: bool = False,
    ) -> Dict[str, Any]:
        """
        Agent-Native invariant consolidation and AST body grounding:
        If `invariants` are passed, persists them as probationary invariants,
        grounds them to AST body hashes, and audits existing invariants for drift.
        """
        now = datetime.now(timezone.utc).isoformat()
        inducted: List[Dict[str, Any]] = []

        if invariants and not dry_run:
            # 1. Update journal/invariants.md
            lines = [f"\n## Updated: {now[:10]} (Probationary Invariant Induction)\n"]
            for inv in invariants:
                domain = inv.get("domain", "General").upper()
                rule = inv.get("rule", "")
                rationale = inv.get("rationale", "")
                lines.append(f"### Invariant [{domain}] (Status: Probationary)")
                lines.append(f"**Rule:** {rule}")
                lines.append(f"**Rationale:** {rationale}\n")

                # Ground to AST if symbol & file provided
                sym = inv.get("symbol")
                fp = inv.get("file_path")
                grounded_rec = None
                if sym and fp:
                    grounded_rec = self.invariant_engine.ground_invariant(
                        domain=domain,
                        rule=rule,
                        rationale=rationale,
                        symbol_name=sym,
                        file_path=fp,
                        trust_level=inv.get("trust_level", "speculative"),
                    )

                inducted.append({
                    "domain": domain,
                    "rule": rule,
                    "rationale": rationale,
                    "status": "probationary",
                    "trust_level": inv.get("trust_level", "speculative"),
                    "ast_hash": grounded_rec.get("ast_hash") if grounded_rec else None,
                })

            with open(INVARIANTS_FILE, "a", encoding="utf-8") as f:
                f.write("\n".join(lines))

            # 2. Persist to FalkorDB
            for item in inducted:
                self._query(
                    self.episodic_db,
                    "MERGE (i:Invariant {rule: $rule}) "
                    "SET i.domain = $domain, i.rationale = $rationale, i.status = $status, "
                    "    i.trust_level = $trust, i.updated_at = $now",
                    {
                        "rule": item.get("rule", ""),
                        "domain": item.get("domain", ""),
                        "rationale": item.get("rationale", ""),
                        "status": item.get("status", "probationary"),
                        "trust": item.get("trust_level", "speculative"),
                        "now": now,
                    },
                )

        # Audit live invariant AST body drift
        drift_report = self.invariant_engine.audit_invariant_drift(quarantine_drifted=(not dry_run))

        # Parse existing invariants from file if none passed
        existing_invariants: List[Dict[str, str]] = []
        if INVARIANTS_FILE.exists():
            content = INVARIANTS_FILE.read_text(encoding="utf-8")
            pattern = re.compile(
                r"###\s+Invariant\s+\[(.*?)\](?:\s*\(.*?\))?\s*\n\*\*Rule:\*\*\s*(.*?)\n\*\*Rationale:\*\*\s*(.*?)(?=\n###|\Z)",
                re.DOTALL,
            )
            for match in pattern.finditer(content):
                domain = match.group(1).strip()
                rule = match.group(2).strip()
                rationale = match.group(3).strip()
                existing_invariants.append({
                    "domain": domain,
                    "rule": rule,
                    "rationale": rationale,
                })

        return {
            "inducted": inducted,
            "active": existing_invariants,
            "drift_audit": drift_report,
        }

    # ── Phase 4: Fact Consolidation (Macro-Truth Induction) ───────────────────

    def consolidate_facts(
        self,
        macro_fact: str,
        superseded_fact_ids: List[str],
        project: str = "kortext",
    ) -> Dict[str, Any]:
        """
        Consolidates fine-grained or redundant episodic facts into a single authoritative macro-truth.
        Creates a new macro-truth fact relationship in FalkorDB with r.is_macro = true, r.project = $project.
        Marks candidate facts in superseded_fact_ids with SET r.superseded = true, r.dormant = true, r.superseded_by = $macro_fact_id.
        """
        macro_fact_id = f"fact_macro_{uuid.uuid4().hex[:10]}"
        now = datetime.now(timezone.utc).isoformat()

        # 1. Update candidate superseded facts
        updated_count = 0
        cand_sub = None
        cand_obj = None

        if superseded_fact_ids:
            # First attempt to find existing subject and object entities from candidate facts
            find_cypher = """
            MATCH (s:Entity)-[r:RELATES_TO]->(t:Entity)
            WHERE r.id IN $ids OR r.fact_id IN $ids OR toString(id(r)) IN $ids
            RETURN s.name, t.name LIMIT 1
            """
            find_rows = self._query(self.episodic_db, find_cypher, {"ids": list(superseded_fact_ids)})
            if find_rows and len(find_rows) > 1 and find_rows[1] and len(find_rows[1][0]) >= 2:
                cand_sub = str(find_rows[1][0][0])
                cand_obj = str(find_rows[1][0][1])

            # Mark candidate facts as superseded and dormant
            update_cypher = """
            UNWIND $ids AS target_id
            MATCH ()-[r:RELATES_TO]->()
            WHERE r.id = target_id OR r.fact_id = target_id OR toString(id(r)) = toString(target_id)
            SET r.superseded = true, r.dormant = true, r.superseded_by = $macro_fact_id
            RETURN count(r)
            """
            res = self._query(
                self.episodic_db,
                update_cypher,
                {"ids": list(superseded_fact_ids), "macro_fact_id": macro_fact_id},
            )
            if res and len(res) > 1 and res[1] and res[1][0]:
                try:
                    updated_count = int(res[1][0][0])
                except (ValueError, TypeError):
                    updated_count = len(superseded_fact_ids)
            else:
                updated_count = len(superseded_fact_ids)

        # 2. Materialize new macro-truth fact relationship
        sub_name = cand_sub or project
        obj_name = cand_obj or "MacroTruth"

        create_cypher = """
        MERGE (s:Entity {name: $sub})
        MERGE (t:Entity {name: $obj})
        CREATE (s)-[r:RELATES_TO {
            id: $macro_fact_id,
            fact: $macro_fact,
            relation: $relation,
            project: $project,
            is_macro: true,
            superseded: false,
            dormant: false,
            importance: 9,
            confidence: 0.98,
            created_at: $now,
            valid_from: $now,
            transaction_time: $now
        }]->(t)
        RETURN id(r)
        """
        self._query(
            self.episodic_db,
            create_cypher,
            {
                "sub": sub_name,
                "obj": obj_name,
                "macro_fact_id": macro_fact_id,
                "macro_fact": macro_fact,
                "relation": "MACRO_FACT",
                "project": project,
                "now": now,
            },
        )

        logger.info(
            f"[DreamEngine] Consolidated {updated_count} facts into macro fact '{macro_fact_id}' for project '{project}'."
        )

        return {
            "status": "ok",
            "macro_fact_id": macro_fact_id,
            "macro_fact": macro_fact,
            "project": project,
            "superseded_count": updated_count,
            "superseded_fact_ids": list(superseded_fact_ids),
        }

    # ── Phase 5: Skill Distillation ───────────────────────────────────────────

    def distill_skill(
        self,
        skill_name: str,
        description: str,
        skill_content: str,
        global_scope: bool = False,
        workspace_root: Optional[str] = None,
    ) -> Path:
        """
        Distills consolidated procedures or patterns into an agent skill specification (SKILL.md)
        with YAML frontmatter (name, description) and markdown body.
        Resolves to global scope (~/.gemini/config/plugins/kortext/skills/<name>) or
        workspace scope (<workspace_root>/.agents/skills/<name>).
        """
        clean_name = skill_name.strip()
        if global_scope:
            dest_dir = Path.home() / ".gemini" / "config" / "plugins" / "kortext" / "skills" / clean_name
        else:
            base_dir = Path(workspace_root) if workspace_root else KORTEXT_ROOT
            dest_dir = base_dir / ".agents" / "skills" / clean_name

        dest_dir.mkdir(parents=True, exist_ok=True)
        skill_file = dest_dir / "SKILL.md"

        stripped_content = skill_content.strip()
        if stripped_content.startswith("---"):
            full_content = stripped_content + "\n"
        else:
            clean_desc = description.strip().replace("\n", " ")
            full_content = f"---\nname: {clean_name}\ndescription: {clean_desc}\n---\n\n{stripped_content}\n"

        skill_file.write_text(full_content, encoding="utf-8")
        logger.info(f"[DreamEngine] Distilled skill '{clean_name}' to: {skill_file}")
        return skill_file

    # ── Full Dream Cycle & Report Generation ─────────────────────────────────

    async def run_dream_cycle(
        self,
        project: str = "kortext",
        purge_stale: bool = True,
        dry_run: bool = False,
        invariants: Optional[List[Dict[str, str]]] = None,
        stale_fact_names: Optional[List[str]] = None,
        consolidations: Optional[List[Dict[str, Any]]] = None,
        distilled_skills: Optional[List[Dict[str, Any]]] = None,
        global_skills: bool = False,
        workspace_root: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Runs cognitive reflection phases, consolidation, and skill distillation (100% Agent-Native)."""
        start_time = datetime.now()
        date_str = start_time.strftime("%Y-%m-%d")

        logger.info(f"[DreamEngine] Initiating Dream Mode for project '{project}' (dry_run={dry_run}, purge_stale={purge_stale})...")

        # Phase 0: Stretched Weibull Retention Decay Sweep
        weibull_dormant = self.sweep_weibull_decay(dry_run=dry_run)
        logger.info(f"[DreamEngine] Phase 0 complete: {weibull_dormant} facts decayed to biological floor ({self.biological_floor}).")

        # Phase 1: Synaptic Pruning & Stale Fact Cleanup
        prune_res = await self.prune_stale_facts(
            purge_stale=purge_stale,
            dry_run=dry_run,
            stale_fact_names=stale_fact_names,
        )
        logger.info(f"[DreamEngine] Phase 1 complete: {prune_res['superseded_count']} facts superseded, {prune_res['archived_count']} archived.")

        # Phase 2: Louvain Subsystem Community Detection
        subsystems = await self.cluster_subsystems(persist=(not dry_run))
        logger.info(f"[DreamEngine] Phase 2 complete: {len(subsystems)} architectural subsystems clustered.")

        # Phase 3: Abstract Invariant Induction & AST Drift Audit
        invariant_results = await self.induce_invariants(invariants=invariants, dry_run=dry_run)
        active_invariants = invariant_results["active"]
        drift_audit = invariant_results["drift_audit"]
        logger.info(f"[DreamEngine] Phase 3 complete: {len(active_invariants)} active invariants, {drift_audit.get('drifted_count', 0)} drifted.")

        # Phase 4: Fact Consolidation
        consolidation_results: List[Dict[str, Any]] = []
        if consolidations:
            for item in consolidations:
                macro_fact = item.get("macro_fact") or item.get("fact")
                superseded_ids = item.get("superseded_fact_ids") or item.get("supersedes") or []
                item_project = item.get("project", project)
                if macro_fact:
                    if not dry_run:
                        res = self.consolidate_facts(
                            macro_fact=macro_fact,
                            superseded_fact_ids=superseded_ids,
                            project=item_project,
                        )
                        consolidation_results.append(res)
                    else:
                        consolidation_results.append({
                            "status": "dry_run",
                            "macro_fact": macro_fact,
                            "superseded_count": len(superseded_ids),
                            "superseded_fact_ids": list(superseded_ids),
                            "project": item_project,
                        })
            logger.info(f"[DreamEngine] Phase 4 complete: {len(consolidation_results)} macro facts consolidated.")

        # Phase 5: Skill Distillation
        distilled_skills_results: List[Dict[str, Any]] = []
        if distilled_skills:
            for s in distilled_skills:
                s_name = s.get("name") or s.get("skill_name") or "unnamed-skill"
                s_desc = s.get("description", "")
                s_content = s.get("content") or s.get("skill_content") or ""
                s_global = s.get("global_scope", global_skills)
                s_ws = s.get("workspace_root", workspace_root)
                if not dry_run:
                    created_path = self.distill_skill(
                        skill_name=s_name,
                        description=s_desc,
                        skill_content=s_content,
                        global_scope=s_global,
                        workspace_root=s_ws,
                    )
                    distilled_skills_results.append({
                        "name": s_name,
                        "description": s_desc,
                        "path": str(created_path),
                        "global_scope": s_global,
                    })
                else:
                    dest_base = (
                        (Path.home() / ".gemini" / "config" / "plugins" / "kortext" / "skills" / s_name)
                        if s_global
                        else ((Path(s_ws) if s_ws else KORTEXT_ROOT) / ".agents" / "skills" / s_name)
                    )
                    distilled_skills_results.append({
                        "name": s_name,
                        "description": s_desc,
                        "path": str(dest_base / "SKILL.md"),
                        "global_scope": s_global,
                        "status": "dry_run",
                    })
            logger.info(f"[DreamEngine] Phase 5 complete: {len(distilled_skills_results)} skills distilled.")

        # Dream Synthesis Report Generation
        duration = (datetime.now() - start_time).total_seconds()
        report_lines = [
            f"# Kortext Dream Report: {date_str}",
            f"**Execution Mode:** {'Dry Run' if dry_run else 'Live Consolidation'} | **Duration:** {duration:.2f}s | **Project:** {project}\n",
            "## 1. Synaptic Pruning & Fact Cleanup",
            f"- **Weibull Dormant Nodes (Floor {self.biological_floor}):** {weibull_dormant}",
            f"- **Facts Superseded:** {prune_res['superseded_count']}",
            f"- **Stale Nodes Purged:** {prune_res['archived_count']}",
        ]
        if prune_res["details"]:
            for d in prune_res["details"]:
                report_lines.append(f"  - *{d['stale_name']}* -> Replaced by **{d['superseded_by']}** ({d['reason']})")
        else:
            report_lines.append("  - No conflicting or stale operational facts detected. Knowledge base is high-density.")

        report_lines.append("\n## 2. Synthesized Architectural Subsystems (Louvain Modularity)")
        for sub in subsystems:
            report_lines.append(f"### Subsystem: {sub['name']} ({sub['file_count']} files)")
            report_lines.append(f"*{sub['description']}*")
            sample_files = [Path(f).name for f in sub['files'][:4]]
            report_lines.append(f"- Member files: `{', '.join(sample_files)}`" + (f" and {len(sub['files'])-4} more..." if len(sub['files']) > 4 else ""))

        report_lines.append("\n## 3. Induced Codebase Invariants")
        if active_invariants:
            for inv in active_invariants:
                report_lines.append(f"- **[{inv.get('domain', 'Core').upper()}]**: {inv.get('rule')}")
                report_lines.append(f"  *Rationale: {inv.get('rationale')}*")
        else:
            report_lines.append("- Existing invariants up-to-date in `cerebrum/journal/invariants.md`.")

        report_lines.append("\n## 4. AST Grounding & Invariant Drift Audit")
        report_lines.append(f"- Grounded invariants: {drift_audit.get('total_grounded', 0)}")
        report_lines.append(f"- Verified: {drift_audit.get('verified_count', 0)}")
        report_lines.append(f"- Drifted / Stale: {drift_audit.get('drifted_count', 0)}")
        report_lines.append(f"- Orphaned: {drift_audit.get('orphaned_count', 0)}")
        if drift_audit.get("drifted"):
            for dr in drift_audit["drifted"]:
                report_lines.append(f"  - [DRIFTED] `{dr.get('symbol_name')}` in `{Path(dr.get('file_path', '')).name}`: rule '{dr.get('rule')[:60]}...'")

        report_lines.append("\n## 5. Consolidated Macro Facts")
        if consolidation_results:
            for c in consolidation_results:
                report_lines.append(f"- **Macro Fact:** {c.get('macro_fact')} (Superseded {c.get('superseded_count', 0)} facts)")
        else:
            report_lines.append("- No fact consolidations performed.")

        report_lines.append("\n## 6. Distilled Agent Skills")
        if distilled_skills_results:
            for s in distilled_skills_results:
                report_lines.append(f"- **Skill:** {s.get('name')} -> `{s.get('path')}`")
        else:
            report_lines.append("- No agent skills distilled.")

        report_md = "\n".join(report_lines)

        report_path_str = "dry-run"
        reports_path_str = "dry-run"
        if not dry_run:
            if workspace_root:
                ws_journal = Path(workspace_root) / "journal"
                target_dreams_dir = ws_journal / "dreams"
                target_reports_dir = ws_journal / "reports"
            else:
                target_dreams_dir = DREAMS_DIR
                target_reports_dir = REPORTS_DIR

            target_dreams_dir.mkdir(parents=True, exist_ok=True)
            target_reports_dir.mkdir(parents=True, exist_ok=True)

            dream_file = target_dreams_dir / f"{date_str}-dream.md"
            with open(dream_file, "w", encoding="utf-8") as f:
                f.write(report_md)
            report_path_str = str(dream_file)

            report_file = target_reports_dir / f"{date_str}-dream.md"
            with open(report_file, "w", encoding="utf-8") as f:
                f.write(report_md)
            reports_path_str = str(report_file)

            logger.info(f"[DreamEngine] Dream Report persisted to: {dream_file}")

        return {
            "status": "ok",
            "duration_seconds": duration,
            "weibull_dormant_count": weibull_dormant,
            "superseded_count": prune_res.get("superseded_count", 0),
            "archived_count": prune_res.get("archived_count", 0),
            "subsystems_count": len(subsystems),
            "subsystem_clusters": len(subsystems),
            "invariants_count": len(active_invariants),
            "invariants_inducted": len(invariant_results.get("inducted", [])),
            "invariant_drift": drift_audit,
            "consolidations": consolidation_results,
            "consolidated_facts_count": len(consolidation_results),
            "distilled_skills": distilled_skills_results,
            "distilled_skills_count": len(distilled_skills_results),
            "markdown_report": report_md,
            "dream_report_path": report_path_str,
            "reports_path": reports_path_str,
            "invariants_path": str(INVARIANTS_FILE),
            "pruned_facts": {
                "active_facts_remaining": prune_res.get("active_count", 0),
                "superseded_facts_pruned": prune_res.get("superseded_count", 0),
                "contradictions_flagged": prune_res.get("contradictions", []),
            },
        }

    # Alias for server & dashboard
    dream = run_dream_cycle


KortextDreamEngine = DreamEngine


class CerebrumDreamEngine(DreamEngine):
    """Deprecated alias for DreamEngine or KortextDreamEngine."""

    def __init__(self, *args, **kwargs):
        warnings.warn(
            "CerebrumDreamEngine is deprecated, use DreamEngine or KortextDreamEngine instead.",
            DeprecationWarning,
            stacklevel=2,
        )
        super().__init__(*args, **kwargs)



def main():
    parser = argparse.ArgumentParser(description="Kortext: dream mode consolidation engine")
    parser.add_argument("--project", default="kortext", help="Project label to consolidate")
    parser.add_argument("--purge-stale", action="store_true", default=True, help="Purge stale facts from FalkorDB and archive to disk")
    parser.add_argument("--dry-run", action="store_true", help="Audit and preview without modifying the database")
    args = parser.parse_args()

    engine = DreamEngine()
    res = asyncio.run(engine.run_dream_cycle(
        project=args.project,
        purge_stale=args.purge_stale,
        dry_run=args.dry_run,
    ))
    logger.info("\n%s", res["markdown_report"])


if __name__ == "__main__":
    main()
