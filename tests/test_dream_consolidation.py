"""
Unit tests for CognitiveDreamEngine and the Stretched Weibull Retention Decay Model.
Verifies retention curves, biological floor enforcement (R_min = 0.05), and consolidation mechanics.
"""

import pytest
from cerebrum.dream import DreamEngine


class TestDreamConsolidation:
    @pytest.fixture
    def dream_engine(self):
        return DreamEngine(
            half_life_hours=72.0,
            shape_parameter=0.65,
            biological_floor=0.05,
        )

    def test_immediate_retention_is_one(self, dream_engine):
        """Verifies that newly asserted facts have full retention (1.0)."""
        retention = dream_engine.compute_retention(elapsed_hours=0.0, importance=5.0)
        assert pytest.approx(retention, rel=1e-3) == 1.0

    def test_weibull_decay_progression(self, dream_engine):
        """Verifies that retention drops smoothly over time."""
        r_24h = dream_engine.compute_retention(elapsed_hours=24.0, importance=5.0)
        r_72h = dream_engine.compute_retention(elapsed_hours=72.0, importance=5.0)
        r_200h = dream_engine.compute_retention(elapsed_hours=200.0, importance=5.0)

        assert 1.0 > r_24h > r_72h > r_200h

    def test_biological_floor_protection(self, dream_engine):
        """Verifies that memories never drop below the biological retention floor (0.05)."""
        # Even after 100,000 hours (over 11 years), retention cannot drop to 0
        r_extreme = dream_engine.compute_retention(elapsed_hours=100000.0, importance=1.0)
        assert r_extreme == 0.05

    def test_importance_scaling(self, dream_engine):
        """Verifies that high-importance facts (S=10) decay significantly slower than low-importance facts (S=1)."""
        r_low = dream_engine.compute_retention(elapsed_hours=100.0, importance=1.0)
        r_high = dream_engine.compute_retention(elapsed_hours=100.0, importance=10.0)

        assert r_high > r_low
