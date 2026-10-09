"""
Unit tests for Weibull Retention integration in RetrievalEngine ranking (RRF).
"""
import pytest
from kortext.retrieval.retention import (
    compute_weibull_retention,
    compute_age_hours,
)
from kortext.retrieval.engine import (
    RetrievalEngine,
    K_RRF,
    W_TEMPORAL,
    W_DENSE,
)


class TestWeibullRetrievalRanking:
    def test_compute_weibull_retention_signature(self):
        """Verifies compute_weibull_retention accepts (age_hours, importance)."""
        # Immediate retention
        r_imm = compute_weibull_retention(age_hours=0.001, importance=5)
        assert pytest.approx(r_imm, 0.01) == 1.0

        # Positional arguments: compute_weibull_retention(age_hours, importance)
        r_pos = compute_weibull_retention(72.0, 10)
        r_pos_low = compute_weibull_retention(72.0, 1)
        assert r_pos > r_pos_low * 1.5

        # Biological floor enforcement
        r_floor = compute_weibull_retention(10000.0, 1)
        assert r_floor == 0.05

    def test_compute_age_hours(self):
        """Verifies compute_age_hours parses ISO timestamps and computes elapsed hours."""
        from datetime import datetime, timezone, timedelta
        now = datetime.now(timezone.utc)
        ts_10h_ago = (now - timedelta(hours=10)).isoformat()
        age = compute_age_hours(ts_10h_ago, reference_time=now)
        assert pytest.approx(age, 0.01) == 10.0

        # Future or None returns 0.0
        assert compute_age_hours(None) == 0.0

    def test_rank_candidates_applies_weibull_decay(self):
        """Verifies that aged facts decay in RRF rank compared to fresh facts."""
        engine = RetrievalEngine()

        # Two facts in the temporal tier: fact_fresh (1h old) vs fact_old (720h old)
        signals = [
            ([
                ("fact_fresh", 1.0, 5),    # age 1h, imp 5 -> retention ~0.96
                ("fact_old", 720.0, 5),    # age 720h, imp 5 -> retention ~0.05
            ], W_TEMPORAL)
        ]

        ranked = engine._rank_candidates(signals)
        assert len(ranked) == 2
        assert ranked[0][0] == "fact_fresh"
        assert ranked[1][0] == "fact_old"
        # fact_fresh score should be dramatically higher than fact_old
        assert ranked[0][1] > ranked[1][1] * 10

    def test_rank_candidates_importance_mitigates_decay(self):
        """Verifies high-importance aged facts retain higher score than low-importance aged facts."""
        engine = RetrievalEngine()

        signals = [
            ([
                ("fact_high_imp", 72.0, 10),  # age 72h, imp 10 -> high retention
                ("fact_low_imp", 72.0, 1),    # age 72h, imp 1 -> low retention
            ], W_TEMPORAL)
        ]

        ranked = engine._rank_candidates(signals)
        assert ranked[0][0] == "fact_high_imp"
        assert ranked[1][0] == "fact_low_imp"
        assert ranked[0][1] > ranked[1][1] * 1.5

    def test_rank_candidates_biological_floor(self):
        """Verifies ancient facts do not drop to zero but retain biological floor mass."""
        engine = RetrievalEngine()

        signals = [
            ([
                ("ancient_fact", 100000.0, 1),
            ], W_TEMPORAL)
        ]

        ranked = engine._rank_candidates(signals)
        assert len(ranked) == 1
        expected_base = W_TEMPORAL / (K_RRF + 1)
        expected_score = expected_base * 0.05
        assert pytest.approx(ranked[0][1], rel=1e-3) == expected_score

    def test_rank_candidates_with_metadata_dict(self):
        """Verifies _rank_candidates accepts candidate_metadata mapping."""
        engine = RetrievalEngine()

        signals = [
            (["fact_alpha", "fact_beta"], W_TEMPORAL)
        ]
        metadata = {
            "fact_alpha": {"age_hours": 720.0, "importance": 1},  # old -> decayed
            "fact_beta": {"age_hours": 0.5, "importance": 5},     # fresh -> high retention
        }

        ranked = engine._rank_candidates(signals, candidate_metadata=metadata)
        # Even though fact_alpha was rank 1 in signal input, fact_beta should overtake it due to retention decay!
        assert ranked[0][0] == "fact_beta"
        assert ranked[1][0] == "fact_alpha"

    def test_retrieve_method_exists_and_calls_query(self):
        """Verifies RetrievalEngine has retrieve() method that delegates to query()."""
        import asyncio
        from unittest.mock import AsyncMock, patch

        async def _run():
            engine = RetrievalEngine()
            with patch.object(engine, "query", AsyncMock(return_value=["res1", "res2"])) as mock_query:
                res = await engine.retrieve("test prompt", collection="test_col")
                assert res == ["res1", "res2"]
                mock_query.assert_called_once_with(prompt="test prompt", collection="test_col")

        asyncio.run(_run())

    def test_weibull_decay_computes_retention_accurately(self):
        """Verifies (strength, delta_t, k, lam) parameter signature matches Weibull formula."""
        initial_strength = 1.0
        elapsed_seconds = 3600.0
        shape_parameter = 0.5
        scale_parameter = 7200.0

        retention = compute_weibull_retention(
            strength=initial_strength,
            delta_t=elapsed_seconds,
            k=shape_parameter,
            lam=scale_parameter,
        )

        assert 0.0 < retention < 1.0
        assert round(retention, 4) == 0.4931

    def test_rank_candidates_with_created_at_metadata(self):
        """Verifies candidates decay based on created_at ISO timestamp."""
        from datetime import datetime, timezone, timedelta
        now = datetime.now(timezone.utc)
        engine = RetrievalEngine()

        ts_fresh = (now - timedelta(hours=1)).isoformat()
        ts_old = (now - timedelta(hours=500)).isoformat()

        signals = [(["item_old", "item_fresh"], W_TEMPORAL)]
        metadata = {
            "item_old": {"created_at": ts_old, "importance": 5},
            "item_fresh": {"created_at": ts_fresh, "importance": 5},
        }

        ranked = engine._rank_candidates(signals, candidate_metadata=metadata)
        assert ranked[0][0] == "item_fresh"
        assert ranked[1][0] == "item_old"
        assert ranked[0][1] > ranked[1][1] * 3

    def test_rank_candidates_with_timestamp_epoch(self):
        """Verifies candidates decay based on unix epoch timestamp."""
        import time
        now_epoch = time.time()
        engine = RetrievalEngine()

        epoch_fresh = now_epoch - 3600  # 1 hour ago
        epoch_old = now_epoch - 3600 * 200  # 200 hours ago

        signals = [(["item_old", "item_fresh"], W_TEMPORAL)]
        metadata = {
            "item_old": {"timestamp": epoch_old, "importance": 5},
            "item_fresh": {"timestamp": epoch_fresh, "importance": 5},
        }

        ranked = engine._rank_candidates(signals, candidate_metadata=metadata)
        assert ranked[0][0] == "item_fresh"
        assert ranked[1][0] == "item_old"

    def test_rank_candidates_with_dict_items(self):
        """Verifies _rank_candidates extracts created_at and importance from dict items."""
        from datetime import datetime, timezone, timedelta
        now = datetime.now(timezone.utc)
        engine = RetrievalEngine()

        signals = [
            ([
                {"text": "doc_old", "created_at": (now - timedelta(hours=400)).isoformat(), "importance": 3},
                {"text": "doc_fresh", "created_at": (now - timedelta(hours=2)).isoformat(), "importance": 8},
            ], W_DENSE)
        ]

        ranked = engine._rank_candidates(signals)
        assert ranked[0][0] == "doc_fresh"
        assert ranked[1][0] == "doc_old"

    def test_rank_candidates_retention_weight_blend(self):
        """Verifies score modulation with blend factor: (1.0 - w) + w * retention."""
        engine = RetrievalEngine()
        signals = [([("doc_old", 1000.0, 1)], W_TEMPORAL)]

        # With retention_weight = 1.0, retention is ~0.05
        ranked_full = engine._rank_candidates(signals, retention_weight=1.0)
        base_rrf = W_TEMPORAL / (K_RRF + 1)
        assert pytest.approx(ranked_full[0][1], rel=1e-2) == base_rrf * 0.05

        # With retention_weight = 0.0, no decay occurs (retention factor = 1.0)
        ranked_none = engine._rank_candidates(signals, retention_weight=0.0)
        assert pytest.approx(ranked_none[0][1], rel=1e-2) == base_rrf * 1.0

        # With retention_weight = 0.5, blend is 0.5 + 0.5 * 0.05 = 0.525
        ranked_half = engine._rank_candidates(signals, retention_weight=0.5)
        assert pytest.approx(ranked_half[0][1], rel=1e-2) == base_rrf * 0.525

    def test_compute_age_seconds(self):
        """Verifies compute_age_seconds returns elapsed age in seconds."""
        from datetime import datetime, timezone, timedelta
        from kortext.retrieval.retention import compute_age_seconds
        now = datetime.now(timezone.utc)
        ts_2h_ago = (now - timedelta(hours=2)).isoformat()
        secs = compute_age_seconds(ts_2h_ago, reference_time=now)
        assert pytest.approx(secs, 1.0) == 7200.0

    def test_rank_candidates_with_valid_from_metadata(self):
        """Verifies candidates decay gracefully when valid_from ISO timestamp is provided."""
        from datetime import datetime, timezone, timedelta
        now = datetime.now(timezone.utc)
        engine = RetrievalEngine()

        ts_fresh = (now - timedelta(hours=2)).isoformat()
        ts_aged = (now - timedelta(hours=300)).isoformat()

        signals = [(["fact_aged", "fact_fresh"], W_TEMPORAL)]
        metadata = {
            "fact_aged": {"valid_from": ts_aged, "importance": 5},
            "fact_fresh": {"valid_from": ts_fresh, "importance": 5},
        }

        ranked = engine._rank_candidates(signals, candidate_metadata=metadata)
        assert ranked[0][0] == "fact_fresh"
        assert ranked[1][0] == "fact_aged"
        assert ranked[0][1] > ranked[1][1] * 2

    def test_rank_candidates_with_delta_t_and_lam(self):
        """Verifies candidates decay with explicit delta_t and lam scale in metadata."""
        engine = RetrievalEngine()
        signals = [(["item_decayed", "item_retained"], W_TEMPORAL)]
        metadata = {
            "item_decayed": {"delta_t": 7200.0, "lam": 1000.0, "k": 0.5, "strength": 1.0},
            "item_retained": {"delta_t": 100.0, "lam": 10000.0, "k": 0.5, "strength": 1.0},
        }

        ranked = engine._rank_candidates(signals, candidate_metadata=metadata)
        assert ranked[0][0] == "item_retained"
        assert ranked[1][0] == "item_decayed"

    def test_rank_candidates_future_or_invalid_timestamp(self):
        """Verifies future or invalid timestamp falls back safely without decay."""
        from datetime import datetime, timezone, timedelta
        now = datetime.now(timezone.utc)
        engine = RetrievalEngine()

        ts_future = (now + timedelta(hours=10)).isoformat()
        signals = [(["doc_future", "doc_invalid", "doc_none"], W_DENSE)]
        metadata = {
            "doc_future": {"timestamp": ts_future},
            "doc_invalid": {"timestamp": "not-a-timestamp"},
            "doc_none": {},
        }

        ranked = engine._rank_candidates(signals, candidate_metadata=metadata)
        assert len(ranked) == 3
        # In the absence of decay, ranks preserve signal order
        assert ranked[0][0] == "doc_future"
        assert ranked[1][0] == "doc_invalid"
        assert ranked[2][0] == "doc_none"

    def test_retrieve_with_retention_weight_delegates_to_query(self):
        """Verifies retrieve() forwards retention_weight parameter to query()."""
        import asyncio
        from unittest.mock import AsyncMock, patch

        async def _run():
            engine = RetrievalEngine()
            with patch.object(engine, "query", AsyncMock(return_value=["res1"])) as mock_query:
                res = await engine.retrieve("test prompt", collection="test_col", retention_weight=0.7)
                assert res == ["res1"]
                mock_query.assert_called_once_with(prompt="test prompt", collection="test_col", retention_weight=0.7)

        asyncio.run(_run())


