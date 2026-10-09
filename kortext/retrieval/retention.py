"""
Stretched Weibull Memory Retention Decay Model.

Governing Equation:
    R(t) = max(exp(-((t / (lambda_h * exp(importance / 10.0))) ** beta)), floor)

Parameters:
    lambda_h: 72.0 hours (nominal 3-day half-life scaling factor)
    beta: 0.65 (stretched exponential shape parameter)
    floor: 0.05 (biological memory floor - memories never decay below 5%)
    importance: 1-10 (scales retention half-life: higher importance retains longer)
"""
from __future__ import annotations

import math
import logging
from datetime import datetime, timezone
from typing import Any, Dict, Optional, Union

logger = logging.getLogger("kortext.retrieval.retention")

# Biological retention decay parameters
DEFAULT_LAMBDA_H: float = 72.0
DEFAULT_BETA: float = 0.65
DEFAULT_FLOOR: float = 0.05
DEFAULT_IMPORTANCE: int = 5


def compute_weibull_retention(
    delta_hours: float = 0.0,
    importance: int = DEFAULT_IMPORTANCE,
    lambda_h: float = DEFAULT_LAMBDA_H,
    beta: float = DEFAULT_BETA,
    floor: float = DEFAULT_FLOOR,
    *,
    age_hours: Optional[float] = None,
    strength: Optional[float] = None,
    delta_t: Optional[float] = None,
    k: Optional[float] = None,
    lam: Optional[float] = None,
) -> float:
    """
    Computes Stretched Weibull Decay memory retention probability with a biological floor.

    Supports dual conventions:
      1. Biological memory formulation:
         R(t) = max(strength * exp(-((delta_hours / (lambda_h * exp(importance / 10.0))) ** beta)), floor)
      2. Classical Weibull decay formulation:
         R(t) = max(strength * exp(-((delta_t / lam) ** k)), floor)

    Args:
        delta_hours: Elapsed time in hours since observation/recording (can also pass as age_hours or delta_t).
        importance: Integer importance weight [1-10] (scales the characteristic decay time).
        lambda_h: Scale parameter in hours (default: 72.0h).
        beta: Stretched exponential shape parameter (default: 0.65).
        floor: Minimum retention probability (biological floor, default: 0.05).
        age_hours: Optional keyword alias for delta_hours.
        strength: Initial memory strength [0.0-1.0] (default: 1.0).
        delta_t: Elapsed time in seconds or hours matching the scale parameter (lam).
        k: Optional alias for shape parameter (beta).
        lam: Optional alias for scale parameter (lambda).

    Returns:
        Retention probability in [floor, 1.0].
    """
    if age_hours is not None:
        delta_hours = age_hours

    eff_delta = delta_t if delta_t is not None else delta_hours

    if eff_delta is None or eff_delta <= 0.0 or math.isnan(eff_delta):
        return float(strength) if strength is not None else 1.0

    eff_strength = float(strength) if strength is not None else 1.0
    eff_shape = float(k) if k is not None else beta

    if lam is not None:
        scale = float(lam)
    else:
        try:
            imp = int(importance) if importance is not None else DEFAULT_IMPORTANCE
        except (ValueError, TypeError):
            imp = DEFAULT_IMPORTANCE

        s_factor = math.exp(imp / 10.0)
        scale = lambda_h * s_factor

    if scale <= 0.0:
        return floor

    try:
        r = eff_strength * math.exp(-((eff_delta / scale) ** eff_shape))
        return min(eff_strength, max(r, floor))
    except (OverflowError, ZeroDivisionError):
        return floor


# Alias matching alternative internal naming conventions
_weibull_retention = compute_weibull_retention


def compute_age_seconds(
    timestamp: Union[str, datetime, int, float, None],
    reference_time: Optional[datetime] = None,
) -> float:
    """
    Computes elapsed age in seconds from an ISO timestamp string, datetime,
    or unix epoch relative to reference_time (default: current UTC).
    """
    return compute_age_hours(timestamp, reference_time=reference_time) * 3600.0



def compute_age_hours(
    timestamp: Union[str, datetime, int, float, None],
    reference_time: Optional[datetime] = None,
) -> float:
    """
    Computes elapsed age in hours from an ISO timestamp string, datetime,
    or unix epoch relative to reference_time (default: current UTC).
    Returns 0.0 if timestamp cannot be parsed or is in the future.
    """
    if timestamp is None:
        return 0.0

    ref = reference_time or datetime.now(timezone.utc)
    if ref.tzinfo is None:
        ref = ref.replace(tzinfo=timezone.utc)

    dt: Optional[datetime] = None

    if isinstance(timestamp, datetime):
        dt = timestamp
    elif isinstance(timestamp, (int, float)):
        # Epoch timestamp in seconds if > 1e8, otherwise treat as already hours
        if timestamp > 1e8:
            try:
                dt = datetime.fromtimestamp(timestamp, tz=timezone.utc)
            except Exception:
                return 0.0
        else:
            return max(0.0, float(timestamp))
    elif isinstance(timestamp, str):
        t_str = timestamp.strip()
        if not t_str:
            return 0.0
        try:
            # Handle numeric string
            val = float(t_str)
            if val > 1e8:
                dt = datetime.fromtimestamp(val, tz=timezone.utc)
            else:
                return max(0.0, val)
        except ValueError:
            pass

        # Try ISO parsing
        try:
            dt = datetime.fromisoformat(t_str.replace("Z", "+00:00"))
        except Exception:
            # Fallback patterns
            for fmt in (
                "%Y-%m-%d %H:%M:%S",
                "%Y-%m-%d %H:%M:%S.%f",
                "%Y-%m-%d",
                "%Y/%m/%d %H:%M:%S",
                "%Y/%m/%d",
            ):
                try:
                    dt = datetime.strptime(t_str, fmt)
                    break
                except ValueError:
                    continue

    if dt is None:
        return 0.0

    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)

    delta = (ref - dt).total_seconds() / 3600.0
    return max(0.0, delta)
