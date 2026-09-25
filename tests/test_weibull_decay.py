"""
Verifies mathematical correctness of the Stretched Weibull Decay Model and Biological Floor.
"""

import math
import pytest


def compute_weibull_retention(delta_hours: float, importance: int, lambda_h: float = 72.0, beta: float = 0.65, floor: float = 0.05) -> float:
    s_factor = math.exp(importance / 10.0)
    scale = lambda_h * s_factor
    r = math.exp(-((delta_hours / scale) ** beta))
    return max(r, floor)


class TestWeibullDecay:
    def test_immediate_retention_is_one(self):
        r = compute_weibull_retention(0.001, importance=5)
        assert pytest.approx(r, 0.01) == 1.0

    def test_importance_scales_retention_half_life(self):
        # A fact with importance 10 should retain significantly more mass at 72 hours than importance 1
        r_imp1 = compute_weibull_retention(72.0, importance=1)
        r_imp10 = compute_weibull_retention(72.0, importance=10)
        assert r_imp10 > r_imp1 * 1.5

    def test_biological_floor_enforcement(self):
        # After 10,000 hours, retention must not fall below the biological floor of 0.05
        r_ancient = compute_weibull_retention(10000.0, importance=1)
        assert r_ancient == 0.05
