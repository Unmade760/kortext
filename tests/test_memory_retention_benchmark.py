"""
Memory Retention Benchmark Suite (MR-1 through MR-6) and Weibull Decay Model Validation.

Covers:
- MR-1, MR-2, MR-3: Weibull Retention Curve, Monotonic Decay, Parameter Checkpoints,
  Importance Half-Life Scaling, Biological Floor Invariant, and Markdown Artifact Generation.
- MR-4: Bi-Temporal Fact Retention (Round-trip Validity Windows and Dormant Fact Supersession).
- MR-5: HippoRAG Associative Personalized PageRank (Multi-hop retention, IDS hub dilution, P95 latency).
- MR-6: End-to-End Token Budget Enforcement (TAA-k Trimming, Seek Symbol Budget, and Session Savings).
"""

from __future__ import annotations

import json
import math
import re
import shutil
import subprocess
import time
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Dict, List, Tuple
from unittest.mock import MagicMock

import numpy as np
import pytest

from kortext.chunking.token_utils import count_tokens
from kortext.episodic.driver import AgentNativeEpisodicDriver
from kortext.falkordb_client import get_shared_falkordb_client
from kortext.retrieval.engine import apply_taak_trimming
from kortext.retrieval.hipporag import HippoRAGPPR
from kortext.symbols.seek import SymbolSeekEngine


def _simulate_rg(cortex_root: Path, target_dir_rel: str, pattern: str) -> str:
    """Fallback text search simulating `rg --no-heading -n <pattern> <target_dir_rel>`."""
    lines = []
    target_dir = cortex_root / target_dir_rel
    try:
        regex = re.compile(pattern)
    except re.error:
        regex = None

    for p in sorted(target_dir.rglob("*")):
        if not p.is_file() or "__pycache__" in p.parts:
            continue
        try:
            rel_str = str(p.relative_to(cortex_root))
            with open(p, "r", encoding="utf-8", errors="ignore") as f:
                for line_num, line in enumerate(f, start=1):
                    matched = regex.search(line) if regex is not None else (pattern in line)
                    if matched:
                        lines.append(f"{rel_str}:{line_num}:{line.rstrip()}")
        except Exception:
            continue
    return "\n".join(lines)


from kortext.retrieval.retention import compute_weibull_retention

# Alias matching alternative internal naming
_weibull_retention = compute_weibull_retention


def _render_ascii_bar(fraction: float, bar_width: int = 15) -> str:
    """Renders a fixed-width Unicode block bar for ASCII visualization."""
    filled = max(0, min(bar_width, int(round(fraction * bar_width))))
    return "█" * filled + "░" * (bar_width - filled)


# ============================================================================
# Test Suite: TestWeibullRetentionCurve (MR-1, MR-2, MR-3)
# ============================================================================

class TestWeibullRetentionCurve:
    """Validates the mathematical invariants of the Stretched Weibull Decay Model."""

    def test_retention_curve_monotonically_decreasing(self):
        """MR-1: Verifies retention is monotonically non-increasing across evaluation horizons."""
        # Arrange: Discrete observation timestamps from immediate to 1 month
        time_horizons = [0.001, 1.0, 6.0, 24.0, 72.0, 168.0, 336.0, 720.0]

        # Act & Assert: For multiple importance tiers, retention must never increase over time
        for importance in [1, 5, 10]:
            retentions = [compute_weibull_retention(t, importance=importance) for t in time_horizons]
            for i in range(len(retentions) - 1):
                assert retentions[i] >= retentions[i + 1], (
                    f"Monotonicity violated at imp={importance} between t={time_horizons[i]}h "
                    f"({retentions[i]:.4f}) and t={time_horizons[i+1]}h ({retentions[i+1]:.4f})"
                )

    @pytest.mark.parametrize(
        "t_hours,min_expected,max_expected",
        [
            (0.001, 0.99, 1.00),  # Immediate retention
            (24.0, 0.65, 0.75),   # 1 Day checkpoint
            (72.0, 0.40, 0.55),   # 3 Day checkpoint (nominal half-life window)
            (168.0, 0.20, 0.35),  # 1 Week checkpoint
            (720.0, 0.05, 0.10),  # 1 Month checkpoint (approaching biological floor)
        ],
    )
    def test_retention_checkpoint_values(
        self, t_hours: float, min_expected: float, max_expected: float
    ):
        """MR-2: Parametrized verification of expected retention ranges at standard checkpoints."""
        # Arrange / Act
        r = compute_weibull_retention(t_hours, importance=5)

        # Assert
        assert min_expected <= r <= max_expected, (
            f"Checkpoint t={t_hours}h produced {r:.4f}, outside expected [{min_expected}, {max_expected}]"
        )

    def test_importance_scales_retention_half_life(self):
        """MR-2: Verifies higher importance facts retain >= 1.5x mass at 72 hours vs baseline."""
        # Arrange
        eval_window_h = 72.0

        # Act
        r_low = compute_weibull_retention(eval_window_h, importance=1)
        r_high = compute_weibull_retention(eval_window_h, importance=10)

        # Assert: High importance (10) must retain at least 1.5x the mass of low importance (1)
        ratio = r_high / r_low
        assert ratio >= 1.50, f"Expected retention ratio >= 1.5x at 72h, got {ratio:.2f}x ({r_high:.4f} / {r_low:.4f})"

    def test_biological_floor_invariant(self):
        """MR-3: Verifies retention never falls below 0.05 biological floor even over deep geological time."""
        # Arrange & Act
        r_10k_imp1 = compute_weibull_retention(10_000.0, importance=1)
        r_100k_imp1 = compute_weibull_retention(100_000.0, importance=1)
        r_100k_imp10 = compute_weibull_retention(100_000.0, importance=10)

        # Assert
        assert r_10k_imp1 == 0.05, f"Expected biological floor 0.05, got {r_10k_imp1}"
        assert r_100k_imp1 == 0.05, f"Expected biological floor 0.05, got {r_100k_imp1}"
        assert r_100k_imp10 == 0.05, f"Expected biological floor 0.05, got {r_100k_imp10}"

    def test_generate_weibull_decay_curve_artifact(self):
        """MR-3: Generates data/weibull_decay_curve.md artifact with ASCII sparkline visualization."""
        # Arrange
        output_file = Path(__file__).resolve().parent.parent / "data" / "weibull_decay_curve.md"
        horizons: List[Tuple[float, str]] = [
            (0.1, "6 minutes"),
            (1.0, "1 hour"),
            (6.0, "6 hours"),
            (12.0, "12 hours"),
            (24.0, "1 day"),
            (48.0, "2 days"),
            (72.0, "3 days (Half-Life)"),
            (168.0, "1 week"),
            (336.0, "2 weeks"),
            (720.0, "1 month"),
            (1000.0, "~41 days"),
        ]

        # Act: Build structured artifact markdown content
        lines = [
            "# Kortext Stretched Weibull Memory Retention Decay Curves",
            "",
            "> Mathematical specification benchmark: Invariants MR-1, MR-2, MR-3.",
            "> Governing Equation: $R(t) = \\max\\left(\\exp\\left(-\\left(\\frac{t}{\\lambda \\cdot e^{I/10}}\\right)^\\beta\\right), \\text{floor}\\right)$",
            "> Parameters: $\\lambda = 72.0\\text{h}$, $\\beta = 0.65$, Biological Floor $= 0.05$ (5%).",
            "",
            "## Retention Profile Comparison Across Importance Tiers",
            "",
            "| Delta (h) | Horizon | Imp 1 Retention | Imp 1 Sparkline | Imp 5 Retention | Imp 5 Sparkline | Imp 10 Retention | Imp 10 Sparkline |",
            "|:---|:---|:---|:---|:---|:---|:---|:---|",
        ]

        for h, label in horizons:
            r1 = compute_weibull_retention(h, importance=1)
            r5 = compute_weibull_retention(h, importance=5)
            r10 = compute_weibull_retention(h, importance=10)

            bar1 = f"`{_render_ascii_bar(r1)}`"
            bar5 = f"`{_render_ascii_bar(r5)}`"
            bar10 = f"`{_render_ascii_bar(r10)}`"

            lines.append(
                f"| {h:7.1f} | {label:18} | {r1 * 100:5.1f}% | {bar1} | {r5 * 100:5.1f}% | {bar5} | {r10 * 100:5.1f}% | {bar10} |"
            )

        lines.extend([
            "",
            "## Architectural Invariants Verified",
            "- **MR-1 (Monotonicity)**: Retention decreases monotonically over time horizons.",
            "- **MR-2 (Importance Half-Life Scaling)**: Importance 10 retains $\\ge 1.5\\times$ more mass at 72 hours than Importance 1.",
            "- **MR-3 (Biological Floor)**: Retention is asymptotic to $0.05$ (5%), preventing catastrophic forgetting of consolidated foundational facts.",
            "",
        ])

        content = "\n".join(lines)
        output_file.parent.mkdir(parents=True, exist_ok=True)
        output_file.write_text(content, encoding="utf-8")

        # Assert
        assert output_file.exists(), f"Artifact file was not created at {output_file}"
        saved_text = output_file.read_text(encoding="utf-8")
        assert len(saved_text) > 500
        assert "Stretched Weibull" in saved_text
        assert "Biological Floor" in saved_text
        assert "Half-Life" in saved_text


# ============================================================================
# Test Suite: TestBiTemporalFactRetention (MR-4)
# ============================================================================

class TestBiTemporalFactRetention:
    """Validates FalkorDB bi-temporal episodic memory retrieval and supersession."""

    @pytest.fixture(autouse=True)
    def setup_driver(self):
        self.driver = AgentNativeEpisodicDriver()
        self.client = get_shared_falkordb_client()

    def test_episodic_fact_write_read_round_trip(self):
        """MR-4: Writes fact with valid_from = now - 1h; queries as_of now (found) vs now - 2h (not found)."""
        # Arrange
        now = datetime.now(timezone.utc)
        t_now = now.isoformat()
        t_minus_1h = (now - timedelta(hours=1)).isoformat()
        t_minus_2h = (now - timedelta(hours=2)).isoformat()

        subject = f"BenchEntity_{uuid.uuid4().hex[:8]}"
        target = f"BenchTarget_{uuid.uuid4().hex[:8]}"
        relation = "USES_PROTOCOL"
        fact_content = f"{subject} uses protocol gRPC v2"

        # Act
        try:
            fact_id = self.driver.record_fact(
                subject=subject,
                relation=relation,
                fact=fact_content,
                object_name=target,
                valid_from=t_minus_1h,
            )
            assert fact_id is not None, "Failed to record fact"

            # Query as of current time (validity window open: t_minus_1h <= t_now)
            active_facts = self.driver.query_facts_as_of(subject=subject, as_of_date=t_now)

            # Query as of 2 hours ago (before valid_from: t_minus_1h > t_minus_2h)
            past_facts = self.driver.query_facts_as_of(subject=subject, as_of_date=t_minus_2h)

            # Assert
            active_ids = [f["fact_id"] for f in active_facts]
            past_ids = [f["fact_id"] for f in past_facts]

            assert fact_id in active_ids, f"Fact {fact_id} should be visible as of now"
            assert fact_id not in past_ids, f"Fact {fact_id} should not be visible before valid_from"

        finally:
            # Clean up created entities and relations in finally block
            self.driver._query(
                "MATCH (e:Entity) WHERE e.name IN [$s, $t] DETACH DELETE e",
                {"s": subject, "t": target},
            )

    def test_superseded_fact_excluded_from_active_query(self):
        """MR-4: Writes old fact, writes new fact superseding old. Verifies old fact has dormant=True."""
        # Arrange
        subject = f"BenchService_{uuid.uuid4().hex[:8]}"
        relation = "CONFIG_PARAM"
        old_fact_content = f"{subject} timeout is 30s"
        new_fact_content = f"{subject} timeout is 60s"

        # Act
        try:
            old_fact_id = self.driver.record_fact(
                subject=subject,
                relation=relation,
                fact=old_fact_content,
            )
            time.sleep(0.01)

            new_fact_id = self.driver.record_fact(
                subject=subject,
                relation=relation,
                fact=new_fact_content,
                supersedes=old_fact_id,
            )
            time.sleep(0.01)

            query_now = datetime.now(timezone.utc).isoformat()
            active_facts = self.driver.query_facts_as_of(subject=subject, as_of_date=query_now)

            # Query dormant state of the old fact directly from graph
            cypher_dormant = "MATCH ()-[r:RELATES_TO {id: $old_id}]->() RETURN r.dormant"
            res_dormant = self.driver._query(cypher_dormant, {"old_id": old_fact_id})

            # Assert
            assert res_dormant and len(res_dormant) > 1 and res_dormant[1], (
                f"Could not locate relationship with id {old_fact_id}"
            )
            dormant_val = res_dormant[1][0][0]
            assert str(dormant_val).lower() == "true", f"Expected r.dormant == true, got {dormant_val}"

            active_ids = [f["fact_id"] for f in active_facts]
            assert old_fact_id not in active_ids, f"Superseded fact {old_fact_id} must be excluded from active query"
            assert new_fact_id in active_ids, f"New fact {new_fact_id} must be returned in active query"

        finally:
            # Clean up created entities in finally block
            self.driver._query(
                "MATCH (e:Entity) WHERE e.name IN [$s, $r] DETACH DELETE e",
                {"s": subject, "r": relation},
            )

    @pytest.mark.anyio
    async def test_unified_fact_filtering_excludes_both_superseded_and_dormant(self):
        """MR-4: Validates unified filtering: facts are active iff coalesce(r.superseded, false)=false AND coalesce(r.dormant, false)=false."""
        now = datetime.now(timezone.utc).isoformat()
        subject = f"UnifiedSubj_{uuid.uuid4().hex[:8]}"
        target = f"UnifiedTgt_{uuid.uuid4().hex[:8]}"
        rel = "PARAM"

        # 1. Active fact: superseded=false, dormant=false
        fact_active_id = self.driver.record_fact(
            subject=subject,
            relation=rel,
            fact=f"{subject} has active_setting",
            object_name=target,
        )

        # 2. Dormant fact (only dormant=true, superseded=false)
        fact_dormant_id = self.driver.record_fact(
            subject=subject,
            relation=rel,
            fact=f"{subject} has dormant_setting",
            object_name=target,
        )
        self.driver._query(
            "MATCH ()-[r:RELATES_TO {id: $id}]->() SET r.dormant = true, r.superseded = false",
            {"id": fact_dormant_id},
        )

        # 3. Superseded fact (only superseded=true, dormant=false)
        fact_superseded_id = self.driver.record_fact(
            subject=subject,
            relation=rel,
            fact=f"{subject} has superseded_setting",
            object_name=target,
        )
        self.driver._query(
            "MATCH ()-[r:RELATES_TO {id: $id}]->() SET r.superseded = true, r.dormant = false",
            {"id": fact_superseded_id},
        )

        try:
            # Test query_multi_hop_facts
            multi_hop = self.driver.query_multi_hop_facts(entity_name=subject, max_hops=1)
            mh_ids = [f["fact_id"] for f in multi_hop]
            assert fact_active_id in mh_ids, "Active fact should be returned in query_multi_hop_facts"
            assert fact_dormant_id not in mh_ids, "Dormant fact must be excluded from query_multi_hop_facts"
            assert fact_superseded_id not in mh_ids, "Superseded fact must be excluded from query_multi_hop_facts"

            # Test search
            search_results = await self.driver.search(query=f"{subject} setting", limit=10)
            search_text = " ".join(search_results)
            assert "active_setting" in search_text, "Active fact should be found in search"
            assert "dormant_setting" not in search_text, "Dormant fact must be excluded from search"
            assert "superseded_setting" not in search_text, "Superseded fact must be excluded from search"
        finally:
            self.driver._query(
                "MATCH (e:Entity) WHERE e.name IN [$s, $t] DETACH DELETE e",
                {"s": subject, "t": target},
            )

    def test_query_facts_as_of_historical_reconstruction(self):
        """MR-4: Verifies point-in-time reconstruction returns historical fact even if currently superseded."""
        subject = f"HistSubj_{uuid.uuid4().hex[:8]}"
        target = f"HistTgt_{uuid.uuid4().hex[:8]}"
        rel = "VERSION"
        t_base = datetime(2026, 1, 1, 12, 0, tzinfo=timezone.utc)
        t_v1_start = t_base.isoformat()
        t_as_of_past = (t_base + timedelta(days=10)).isoformat()
        t_v2_start = (t_base + timedelta(days=30)).isoformat()
        t_as_of_present = (t_base + timedelta(days=40)).isoformat()

        try:
            # Fact 1: valid from Jan 1
            f1_id = self.driver.record_fact(
                subject=subject,
                relation=rel,
                fact=f"{subject} version is 1.0",
                object_name=target,
                valid_from=t_v1_start,
            )

            # Fact 2: supersedes Fact 1 starting Jan 31
            f2_id = self.driver.record_fact(
                subject=subject,
                relation=rel,
                fact=f"{subject} version is 2.0",
                object_name=target,
                valid_from=t_v2_start,
                supersedes=f1_id,
            )
            # Adjust f1 valid_to to match the transition point t_v2_start
            self.driver._query(
                "MATCH ()-[r:RELATES_TO {id: $id}]->() SET r.valid_to = $v_end",
                {"id": f1_id, "v_end": t_v2_start},
            )

            # Query historical point-in-time: Jan 11 (f1 was valid, f2 did not exist yet)
            past_facts = self.driver.query_facts_as_of(subject=subject, as_of_date=t_as_of_past)
            past_ids = [f["fact_id"] for f in past_facts]
            assert f1_id in past_ids, "Historical query must return f1 even though it is currently superseded"
            assert f2_id not in past_ids, "Historical query must not return future fact f2"

            # Query present point-in-time: Feb 10 (f1 validity expired, f2 is active)
            present_facts = self.driver.query_facts_as_of(subject=subject, as_of_date=t_as_of_present)
            present_ids = [f["fact_id"] for f in present_facts]
            assert f1_id not in present_ids, "Present query must exclude expired fact f1"
            assert f2_id in present_ids, "Present query must return active fact f2"

        finally:
            self.driver._query(
                "MATCH (e:Entity) WHERE e.name IN [$s, $t] DETACH DELETE e",
                {"s": subject, "t": target},
            )

    def test_delete_fact_by_id_marks_relationship_and_episodic_superseded(self):
        """MR-4: Verifies delete_fact matches by relation ID and marks r.superseded = true."""
        import asyncio

        subject = f"DeleteSubj_{uuid.uuid4().hex[:8]}"
        target = f"DeleteTgt_{uuid.uuid4().hex[:8]}"
        relation = "CONNECTED_TO"
        fact_content = f"{subject} is connected to {target}"
        reason = "Decommissioned connection"

        try:
            fact_id = self.driver.record_fact(
                subject=subject,
                relation=relation,
                fact=fact_content,
                object_name=target,
            )
            assert fact_id.startswith("fact_")

            # Act: Delete the fact by its fact_id
            asyncio.run(self.driver.delete_fact(fact_id=fact_id, reason=reason))

            # Query relationship edge directly
            cypher_edge = "MATCH ()-[r:RELATES_TO {id: $id}]->() RETURN r.superseded, r.superseded_reason"
            res = self.driver._query(cypher_edge, {"id": fact_id})
            assert res and len(res) > 1 and res[1], f"Could not find relationship edge {fact_id}"
            superseded, actual_reason = res[1][0][0], res[1][0][1]
            assert str(superseded).lower() == "true", f"Expected r.superseded == true, got {superseded}"
            assert actual_reason == reason

            # Also verify episodic node deletion by episode name/id
            ep_name = f"DeleteEp_{uuid.uuid4().hex[:8]}"
            asyncio.run(
                self.driver.record_outcome(
                    episode_name=ep_name,
                    content="Episode about to be superseded",
                )
            )
            asyncio.run(self.driver.delete_fact(fact_id=ep_name, reason="Outdated episode"))

            cypher_ep = "MATCH (e:Episodic {name: $name}) RETURN e.superseded, e.superseded_reason"
            res_ep = self.driver._query(cypher_ep, {"name": ep_name})
            assert res_ep and len(res_ep) > 1 and res_ep[1], f"Could not find episodic node {ep_name}"
            ep_superseded, ep_reason = res_ep[1][0][0], res_ep[1][0][1]
            assert str(ep_superseded).lower() == "true", f"Expected e.superseded == true, got {ep_superseded}"
            assert ep_reason == "Outdated episode"

            # Also verify relationship edge deletion by fact text substring
            fact_text_unique = f"UniqueSubstring_{uuid.uuid4().hex[:8]}"
            fact_id2 = self.driver.record_fact(
                subject=subject,
                relation="SUB_REL",
                fact=f"{subject} has property {fact_text_unique}",
                object_name=target,
            )
            asyncio.run(self.driver.delete_fact(fact_id=fact_text_unique, reason="Text superseded"))
            res2 = self.driver._query(cypher_edge, {"id": fact_id2})
            assert res2 and len(res2) > 1 and res2[1]
            assert str(res2[1][0][0]).lower() == "true"
            assert res2[1][0][1] == "Text superseded"

        finally:
            self.driver._query(
                "MATCH (e:Entity) WHERE e.name IN [$s, $t] DETACH DELETE e",
                {"s": subject, "t": target},
            )
            if "ep_name" in locals():
                self.driver._query(
                    "MATCH (e:Episodic {name: $name}) DETACH DELETE e",
                    {"name": ep_name},
                )

    def test_query_facts_as_of_temporal_ordering(self):
        """MR-4: Verifies query_facts_as_of returns facts sorted by valid_from DESC."""
        now = datetime.now(timezone.utc)
        t_now = now.isoformat()
        t_2022 = (now - timedelta(days=700)).isoformat()
        t_2023 = (now - timedelta(days=350)).isoformat()
        t_2024 = (now - timedelta(days=10)).isoformat()

        subject = f"TemporalOrderSubj_{uuid.uuid4().hex[:8]}"
        target = f"TemporalOrderTarget_{uuid.uuid4().hex[:8]}"
        relation = "ROLE_PROGRESSION"

        try:
            # Insert in non-chronological order
            self.driver.record_fact(
                subject=subject,
                relation=relation,
                fact=f"{subject} was engineer in 2022",
                object_name=target,
                valid_from=t_2022,
            )
            self.driver.record_fact(
                subject=subject,
                relation=relation,
                fact=f"{subject} was lead in 2024",
                object_name=target,
                valid_from=t_2024,
            )
            self.driver.record_fact(
                subject=subject,
                relation=relation,
                fact=f"{subject} was senior in 2023",
                object_name=target,
                valid_from=t_2023,
            )

            facts = self.driver.query_facts_as_of(subject=subject, as_of_date=t_now)
            assert len(facts) == 3, f"Expected 3 facts, got {len(facts)}"
            # Verify strict descending order by valid_from
            dates = [f["valid_from"] for f in facts]
            assert dates == sorted(dates, reverse=True), f"Facts not sorted descending by valid_from: {dates}"
            assert "2024" in facts[0]["fact"]
            assert "2023" in facts[1]["fact"]
            assert "2022" in facts[2]["fact"]
        finally:
            self.driver._query(
                "MATCH (e:Entity) WHERE e.name IN [$s, $t] DETACH DELETE e",
                {"s": subject, "t": target},
            )

    @pytest.mark.anyio
    async def test_episodic_search_temporal_ordering(self):
        """MR-4: Verifies search ranks newer matching facts above older ones when relevance scores tie."""
        now = datetime.now(timezone.utc)
        t_older = (now + timedelta(seconds=1)).isoformat()
        t_newer = (now + timedelta(seconds=2)).isoformat()

        subject = f"TemporalSearchSubj_{uuid.uuid4().hex[:8]}"
        target = f"TemporalSearchTarget_{uuid.uuid4().hex[:8]}"
        relation = "STATUS"
        unique_term = f"uniquekeyword{uuid.uuid4().hex[:6]}"

        try:
            self.driver.record_fact(
                subject=subject,
                relation=relation,
                fact=f"{subject} historical fact with {unique_term}",
                object_name=target,
                valid_from=t_older,
            )
            self.driver.record_fact(
                subject=subject,
                relation=relation,
                fact=f"{subject} current fact with {unique_term}",
                object_name=target,
                valid_from=t_newer,
            )

            results = await self.driver.search(unique_term, limit=5)
            assert len(results) >= 2, f"Expected at least 2 matching facts, got {len(results)}"
            # Newer fact should be ranked before older fact
            assert "current fact" in results[0], f"Expected newest fact first, got: {results}"
            assert "historical fact" in results[1], f"Expected older fact second, got: {results}"
        finally:
            self.driver._query(
                "MATCH (e:Entity) WHERE e.name IN [$s, $t] DETACH DELETE e",
                {"s": subject, "t": target},
            )

    def test_transitive_invalidation_marks_dependent_facts_provisional_stale(self):
        """MR-4: Invalidation marks 1-hop outgoing facts connected to superseded object as provisional_stale=True."""
        s_name = f"TransSubj_{uuid.uuid4().hex[:8]}"
        mid_name = f"TransMid_{uuid.uuid4().hex[:8]}"
        down_name = f"TransDown_{uuid.uuid4().hex[:8]}"

        try:
            # S -> Mid (fact 1)
            old_fid = self.driver.record_fact(
                subject=s_name,
                relation="CONNECTED_TO",
                fact=f"{s_name} connects to {mid_name}",
                object_name=mid_name,
            )
            # Mid -> Down (fact 2, outgoing from Mid)
            dep_fid = self.driver.record_fact(
                subject=mid_name,
                relation="HOSTS_SERVICE",
                fact=f"{mid_name} hosts {down_name}",
                object_name=down_name,
            )

            # Supersede old_fid with a new fact
            new_fid = self.driver.record_fact(
                subject=s_name,
                relation="CONNECTED_TO",
                fact=f"{s_name} now connects to a different service",
                object_name=mid_name,
                supersedes=old_fid,
            )

            # Verify dep_fid has provisional_stale = true
            res = self.driver._query(
                "MATCH ()-[r:RELATES_TO {id: $fid}]->() RETURN r.provisional_stale",
                {"fid": dep_fid},
            )
            assert res and len(res) > 1 and res[1], f"Could not find relationship {dep_fid}"
            val = res[1][0][0]
            assert str(val).lower() == "true", f"Expected r.provisional_stale == true, got {val}"

        finally:
            self.driver._query(
                "MATCH (e:Entity) WHERE e.name IN [$s, $m, $d] DETACH DELETE e",
                {"s": s_name, "m": mid_name, "d": down_name},
            )

    @pytest.mark.anyio
    async def test_episodic_search_weibull_retention_ranking(self):
        """MR-4: Verifies Weibull retention decay ranks recent fact above an identical-relevance old fact."""
        now = datetime.now(timezone.utc)
        # Old fact from 30 days ago (720 hours)
        t_old = (now - timedelta(days=30)).isoformat()
        # Fresh fact from 1 hour ago
        t_fresh = (now - timedelta(hours=1)).isoformat()

        subject = f"WeibullSearchSubj_{uuid.uuid4().hex[:8]}"
        target = f"WeibullSearchTarget_{uuid.uuid4().hex[:8]}"
        relation = "STATUS"
        unique_term = f"weibullterm{uuid.uuid4().hex[:6]}"

        try:
            self.driver.record_fact(
                subject=subject,
                relation=relation,
                fact=f"{subject} old stale entry with {unique_term}",
                object_name=target,
                valid_from=t_old,
                importance=5,
            )
            self.driver.record_fact(
                subject=subject,
                relation=relation,
                fact=f"{subject} fresh recent entry with {unique_term}",
                object_name=target,
                valid_from=t_fresh,
                importance=5,
            )

            results = await self.driver.search(unique_term, limit=5)
            assert len(results) >= 2, f"Expected 2 matching facts, got {len(results)}"
            # Fresh fact must rank first due to Weibull retention modulation
            assert "fresh recent entry" in results[0], f"Expected fresh fact first due to Weibull retention, got {results}"
            assert "old stale entry" in results[1], f"Expected old fact second due to Weibull decay, got {results}"
        finally:
            self.driver._query(
                "MATCH (e:Entity) WHERE e.name IN [$s, $t] DETACH DELETE e",
                {"s": subject, "t": target},
            )


# ============================================================================
# Test Suite: TestHippoRAGAssociativeRetention (MR-5)
# ============================================================================

class TestHippoRAGAssociativeRetention:
    """Validates HippoRAG Personalized PageRank associative retrieval over cerebrum_symbols."""

    @pytest.fixture(autouse=True)
    def setup_hipporag(self):
        self.ppr = HippoRAGPPR()

    def test_ppr_retention_across_2_hops(self):
        """MR-5: Seeds ['RetrievalEngine'], verifies >= 1 associative node with score > 0.01."""
        # Arrange
        seeds = ["RetrievalEngine"]

        # Act
        results = self.ppr.retrieve_associative_subgraph(
            seed_entities=seeds,
            top_k=15,
            graph_name="cerebrum_symbols",
        )

        # Assert: Associative (non-seed) nodes must be discovered with non-trivial mass
        associative_nodes = [r for r in results if r[0] not in seeds]
        assert len(associative_nodes) >= 1, "Expected at least 1 associative 2-hop node to be retrieved"
        assert any(score > 0.01 for _, score in associative_nodes), (
            f"Expected at least one associative node with score > 0.01, got: {associative_nodes}"
        )

    def test_ppr_seed_specificity_vs_hub_dilution(self):
        """MR-5: Verifies Inverse Degree Specificity (IDS) prevents high-degree hubs from drowning specific nodes."""
        # Arrange: RetrievalEngine is a specific symbol; main is a high-degree hub
        seeds = ["RetrievalEngine", "main"]

        # Act
        results = dict(
            self.ppr.retrieve_associative_subgraph(
                seed_entities=seeds,
                top_k=20,
                graph_name="cerebrum_symbols",
            )
        )

        # Assert: RetrievalEngine must receive significantly higher score than generic hub 'main'
        score_specific = results.get("RetrievalEngine", 0.0)
        score_hub = results.get("main", 0.0)

        assert score_specific > score_hub * 2.0, (
            f"IDS failed to protect specific node: RetrievalEngine ({score_specific:.4f}) vs main ({score_hub:.4f})"
        )

    def test_ppr_latency_under_load_p95(self):
        """MR-5: Runs 30 iterations of PPR and verifies p50 < 10ms and p95 < 30ms under load."""
        # Arrange
        iterations = 30
        latencies_ms: List[float] = []

        # Act
        for _ in range(iterations):
            t0 = time.perf_counter()
            self.ppr.retrieve_associative_subgraph(
                seed_entities=["RetrievalEngine"],
                top_k=10,
                graph_name="cerebrum_symbols",
            )
            latencies_ms.append((time.perf_counter() - t0) * 1000.0)

        # Assert
        p50 = float(np.percentile(latencies_ms, 50))
        p95 = float(np.percentile(latencies_ms, 95))

        assert p50 < 10.0, f"HippoRAG PPR p50 latency exceeded budget: {p50:.2f}ms (target < 10ms)"
        assert p95 < 30.0, f"HippoRAG PPR p95 latency exceeded budget: {p95:.2f}ms (target < 30ms)"


# ============================================================================
# Test Suite: TestE2ETokenBudget (MR-6)
# ============================================================================

class TestE2ETokenBudget:
    """Validates token budget limits and savings across TAA-k, seek_symbol, and full sessions."""

    def test_taak_token_budget_enforcement(self):
        """MR-6: 30 candidates, verifies trimmed <= 15 and >= 50% token reduction."""
        # Arrange: 30 candidates with a sharp drop off after candidate 5
        candidates = []
        for i in range(30):
            if i < 5:
                score = 0.50 - i * 0.02
            else:
                score = 0.05 - (i - 5) * 0.001
            doc_text = f"Candidate document {i} containing dense architectural specifications and metadata. " * 4
            candidates.append((doc_text, score))

        orig_token_count = count_tokens("\n".join(c[0] for c in candidates))

        # Act: Apply Truncation-Aware Adaptive Knee trimming
        trimmed = apply_taak_trimming(candidates, k_min=3, k_max=15)
        trimmed_token_count = count_tokens("\n".join(trimmed))

        # Assert
        assert len(trimmed) <= 15, f"TAA-k exceeded maximum k_max threshold: {len(trimmed)} > 15"
        reduction = (orig_token_count - trimmed_token_count) / orig_token_count
        assert reduction >= 0.50, (
            f"TAA-k failed to achieve >= 50% token reduction: {reduction * 100:.2f}% "
            f"({orig_token_count} -> {trimmed_token_count} tokens)"
        )

    def test_seek_symbol_token_budget_under_150(self):
        """MR-6: SymbolSeekEngine().seek_symbol('RetrievalEngine') tokens < 150."""
        # Arrange
        engine = SymbolSeekEngine()

        # Act
        output = engine.seek_symbol("RetrievalEngine")

        # Assert: Output must be valid JSON containing match and word tokens strictly < 150
        data = json.loads(output)
        assert data["status"] == "found"
        assert len(data["matches"]) >= 1
        assert data["matches"][0]["symbol"] == "RetrievalEngine"

        word_tokens = len(output.split())
        assert word_tokens < 150, f"seek_symbol exceeded 150 token budget: {word_tokens} words"

    def test_aggregate_session_token_savings(self):
        """MR-6: Simulates 8 symbol queries with live rg vs seek_symbol, asserts overall savings >= 0.85 or 0.90."""
        # Arrange
        cortex_root = Path(__file__).resolve().parent.parent
        symbols = [
            "RetrievalEngine",
            "SymbolSeekEngine",
            "HippoRAGPPR",
            "AgentNativeEpisodicDriver",
            "FalkorDBClient",
            "CausalSanitizer",
            "apply_taak_trimming",
            "extract_symbol_candidates",
        ]
        engine = SymbolSeekEngine()

        total_rg_tokens = 0
        total_seek_tokens = 0

        pkg_dir = "kortext"
        # Act
        for sym in symbols:
            # 1. Run live ripgrep and accumulate matched files content (agent inspection volume)
            if shutil.which("rg"):
                rg_res = subprocess.run(
                    ["rg", "--no-heading", sym, pkg_dir],
                    cwd=cortex_root,
                    capture_output=True,
                    text=True,
                )
                rg_text = rg_res.stdout
            else:
                rg_text = _simulate_rg(cortex_root, pkg_dir, sym)

            matched_files = sorted({line.split(":", 1)[0] for line in rg_text.splitlines() if ":" in line})
            for f in matched_files:
                fpath = cortex_root / f
                if fpath.is_file():
                    rg_text += "\n" + fpath.read_text(encoding="utf-8")

            rg_tokens = count_tokens(rg_text)
            total_rg_tokens += rg_tokens

            # 2. Run deterministic AST seek_symbol
            seek_out = engine.seek_symbol(sym)
            seek_tokens = count_tokens(seek_out)
            total_seek_tokens += seek_tokens

        # Assert: Over an 8-symbol session, AST seek achieves >= 90% token reduction over file-loading rg
        savings_ratio = (total_rg_tokens - total_seek_tokens) / total_rg_tokens
        assert savings_ratio >= 0.90, (
            f"Aggregate token savings {savings_ratio * 100:.2f}% below 90% requirement "
            f"({total_rg_tokens} rg tokens vs {total_seek_tokens} seek tokens)"
        )
