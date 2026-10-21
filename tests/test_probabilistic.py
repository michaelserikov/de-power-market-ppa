"""Offline tests for v0.6: quantile scores, coverage tests and the forecast-driven battery."""

import numpy as np
import pandas as pd
import pytest

from deppa import probabilistic as pr


def test_pinball_and_coverage_of_a_correct_distribution():
    rng = np.random.default_rng(2)
    days = pd.date_range("2024-01-01", periods=300, freq="D")
    actual = pd.DataFrame(rng.normal(0, 1, (300, 24)), index=days, columns=range(24))
    from scipy.stats import norm
    qf = {q: pd.DataFrame(norm.ppf(q), index=days, columns=range(24)) for q in pr.LEVELS}
    cov = pr.coverage(actual, qf, 0.8)
    assert cov["coverage"] == pytest.approx(0.8, abs=0.02) and cov["kupiec_p"] > 0.01
    wrong = {q: f * 0.3 for q, f in qf.items()}                       # far too narrow
    assert pr.pinball(actual, qf) < pr.pinball(actual, wrong)
    assert pr.coverage(actual, wrong, 0.8)["kupiec_p"] < 1e-6


def test_battery_on_perfect_forecast_equals_perfect_profit():
    rng = np.random.default_rng(3)
    days = pd.date_range("2024-01-01", periods=5, freq="D")
    actual = pd.DataFrame(rng.normal(80, 30, (5, 24)), index=days, columns=range(24))
    v = pr.battery_value(actual, {"same": actual, "flat": actual * 0 + 70})
    assert np.allclose(v["same"], v["perfect"])
    assert (v["flat"] <= v["perfect"] + 1e-9).all()
