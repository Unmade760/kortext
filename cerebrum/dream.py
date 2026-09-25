"""
Dream mode: offline memory reflection, synaptic pruning, and subsystem synthesis.

100% Agent-Native:
- Contradiction auditing and invariant induction are driven directly by the frontier Antigravity agent.
- Zero local LLM chat completion dependencies on :8000 (reserving Metal GPU for embeddings & reranking).
- Louvain Subsystem Community Detection is fully deterministic and runs in <5ms.
- Synaptic pruning archives superseded FalkorDB nodes into markdown and purges them.

Can be triggered on-demand via:
1. CLI: python -m cerebrum.dream [--project cerebrum] [--purge-stale] [--dry-run]
2. Antigravity Agent MCP Tool: trigger_dream_mode(project, purge_stale, dry_run, invariants, stale_fact_names)
3. Cerebrum Dashboard: 'Trigger Dream Mode' button on http://localhost:8004
"""
from __future__ import annotations

import argparse
import asyncio
import json
import os
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional
import redis

import math
from cerebrum.symbols.clustering import SubsystemClusterer
from cerebrum.falkordb_client import FalkorDBClient, FALKORDB_HOST, FALKORDB_PORT, FALKORDB_PASS
from cerebrum.invariants import InvariantGroundingEngine

FALKORDB_DB   = os.getenv("FALKORDB_DATABASE", "cerebrum")

CEREBRUM_ROOT   = Path(__file__).resolve().parent.parent
JOURNAL_DIR   = Path(os.getenv("JOURNAL_DIR", str(CEREBRUM_ROOT / "journal")))
ARCHIVE_DIR   = JOURNAL_DIR / "archive"
DREAMS_DIR    = JOURNAL_DIR / "dreams"
INVARIANTS_FILE = JOURNAL_DIR / "invariants.md"


class DreamEngine:
    """The cognitive consolidation and reflection engine for Cerebrum (Agent-Native)."""

    def __init__(
        self,
        host: str = FALKORDB_HOST,
        port: int = FALKORDB_PORT,
        password: Optional[str] = FALKORDB_PASS,
        episodic_db: str = FALKORDB_DB,
        symbols_db: str = "cerebrum_symbols",
        half_life_hours: float = 72.0,
        shape_parameter: float = 0.65,
        biological_floor: float = 0.05,
    ):
        self.host = host
        self.port = port
        self.password = password or None
        self.episodic_db = episodic_db
        self.symbols_db = symbols_db
        self.half_life_hours = half_life_hours
        self.shape_parameter = shape_parameter
        self.biological_floor = biological_floor
        self.client = FalkorDBClient(host=self.host, port=self.port, password=self.password)
        self.invariant_engine = InvariantGroundingEngine(
            host=self.host,
            port=self.port,
            password=self.password,
            db_name=self.episodic_db,
        )

        ARCHIVE_DIR.mkdir(parents=True, exist_ok=True)
        DREAMS_DIR.mkdir(parents=True, exist_ok=True)

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
            # 1. Update cerebrum/journal/invariants.md
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

    # ── Phase 4: Full Dream Cycle & Report Generation ─────────────────────────

    async def run_dream_cycle(
        self,
        project: str = "cerebrum",
        purge_stale: bool = True,
        dry_run: bool = False,
        invariants: Optional[List[Dict[str, str]]] = None,
        stale_fact_names: Optional[List[str]] = None,
    ) -> Dict[str, Any]:
        """Runs all four cognitive reflection phases on-demand (100% Agent-Native)."""
        start_time = datetime.now()
        date_str = start_time.strftime("%Y-%m-%d")

        print(f"[DreamEngine] Initiating Dream Mode for project '{project}' (dry_run={dry_run}, purge_stale={purge_stale})...")

        # Phase 0: Stretched Weibull Retention Decay Sweep
        weibull_dormant = self.sweep_weibull_decay(dry_run=dry_run)
        print(f"[DreamEngine] Phase 0 complete: {weibull_dormant} facts decayed to biological floor ({self.biological_floor}).")

        # Phase 1: Synaptic Pruning & Stale Fact Cleanup
        prune_res = await self.prune_stale_facts(
            purge_stale=purge_stale,
            dry_run=dry_run,
            stale_fact_names=stale_fact_names,
        )
        print(f"[DreamEngine] Phase 1 complete: {prune_res['superseded_count']} facts superseded, {prune_res['archived_count']} archived.")

        # Phase 2: Louvain Subsystem Community Detection
        subsystems = await self.cluster_subsystems(persist=(not dry_run))
        print(f"[DreamEngine] Phase 2 complete: {len(subsystems)} architectural subsystems clustered.")

        # Phase 3: Abstract Invariant Induction & AST Drift Audit
        invariant_results = await self.induce_invariants(invariants=invariants, dry_run=dry_run)
        active_invariants = invariant_results["active"]
        drift_audit = invariant_results["drift_audit"]
        print(f"[DreamEngine] Phase 3 complete: {len(active_invariants)} active invariants, {drift_audit.get('drifted_count', 0)} drifted.")

        # Phase 4: Dream Synthesis Report
        duration = (datetime.now() - start_time).total_seconds()
        report_lines = [
            f"# Cerebrum Dream Report: {date_str}",
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

        report_md = "\n".join(report_lines)

        report_path_str = "dry-run"
        if not dry_run:
            report_file = DREAMS_DIR / f"{date_str}-dream.md"
            with open(report_file, "w", encoding="utf-8") as f:
                f.write(report_md)
            report_path_str = str(report_file)
            print(f"[DreamEngine] Dream Report persisted to: {report_file}")

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
            "markdown_report": report_md,
            "dream_report_path": report_path_str,
            "invariants_path": str(INVARIANTS_FILE),
            "pruned_facts": {
                "active_facts_remaining": prune_res.get("active_count", 0),
                "superseded_facts_pruned": prune_res.get("superseded_count", 0),
                "contradictions_flagged": prune_res.get("contradictions", []),
            },
        }

    # Alias for server & dashboard
    dream = run_dream_cycle


CerebrumDreamEngine = DreamEngine


def main():
    parser = argparse.ArgumentParser(description="Cerebrum: dream mode consolidation engine")
    parser.add_argument("--project", default="cerebrum", help="Project label to consolidate")
    parser.add_argument("--purge-stale", action="store_true", default=True, help="Purge stale facts from FalkorDB and archive to disk")
    parser.add_argument("--dry-run", action="store_true", help="Audit and preview without modifying the database")
    args = parser.parse_args()

    engine = DreamEngine()
    res = asyncio.run(engine.run_dream_cycle(
        project=args.project,
        purge_stale=args.purge_stale,
        dry_run=args.dry_run,
    ))
    print("\n" + res["markdown_report"])


if __name__ == "__main__":
    main()
