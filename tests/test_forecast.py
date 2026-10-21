"""Offline tests for v0.5: local-day matrices on clock-change days, the naive rule, LEAR on a
synthetic market and forecast evaluation."""

import numpy as np
import pandas as pd
import pytest

from deppa import forecast as fc


def test_daily_matrix_fixes_clock_change_days():
    ts = pd.date_range("2025-03-29 23:00", "2025-03-30 21:00", freq="h", tz="UTC")   # local 30 March: 23 hours
    df = pd.DataFrame({"ts_utc": ts, "x": np.arange(len(ts), dtype=float)})
    m = fc.daily_matrix(df, "x")
    day = m.loc["2025-03-30"]
    assert len(day) == 24 and not day.isna().any()
    assert day[2] == pytest.approx((day[1] + day[3]) / 2)                             # interpolated missing hour
    ts = pd.date_range("2025-10-25 22:00", "2025-10-26 22:00", freq="h", tz="UTC")   # local 26 October: 25 hours
    df = pd.DataFrame({"ts_utc": ts, "x": np.arange(len(ts), dtype=float)})
    day = fc.daily_matrix(df, "x").loc["2025-10-26"]
    assert len(day) == 24 and day[2] == pytest.approx((2 + 3) / 2)                   # doubled hour averaged


def test_naive_uses_last_week_on_monday_and_yesterday_midweek():
    days = pd.date_range("2025-01-01", "2025-01-20", freq="D")
    price = pd.DataFrame(np.outer(np.arange(len(days)), np.ones(24)), index=days, columns=range(24))
    n = fc.naive(price, pd.DatetimeIndex(["2025-01-13", "2025-01-15"]))    # Monday, Wednesday
    assert n.loc["2025-01-13", 0] == price.loc["2025-01-06", 0]
    assert n.loc["2025-01-15", 0] == price.loc["2025-01-14", 0]


def _synthetic_inputs(n_days=500, seed=0):
    rng = np.random.default_rng(seed)
    days = pd.date_range("2023-01-01", periods=n_days, freq="D")
    load = pd.DataFrame(50_000 + 8_000 * np.sin(np.arange(24) / 24 * 2 * np.pi)[None, :] + rng.normal(0, 2_000, (n_days, 24)),
                        index=days, columns=range(24))
    res = pd.DataFrame(rng.uniform(5_000, 40_000, (n_days, 24)), index=days, columns=range(24))
    price = 40 + 0.0025 * (load - res) + rng.normal(0, 3, (n_days, 24))
    const = pd.Series(70.0, index=days)
    return {"price": price, "load": load, "res": res, "eua": const, "gas": const + rng.normal(0, 1e-3, n_days)}


def test_lear_learns_a_fundamental_market_better_than_naive():
    inp = _synthetic_inputs()
    days = pd.date_range("2024-03-01", periods=14, freq="D")
    actual = inp["price"].loc[days]
    lear = fc.lear(inp, days, 364)
    m = fc.metrics(actual, lear, fc.naive(inp["price"], days))
    assert m["rmae"] < 0.5 and m["mae"] < 5


def test_metrics_and_diebold_mariano():
    rng = np.random.default_rng(1)
    days = pd.date_range("2024-01-01", periods=200, freq="D")
    actual = pd.DataFrame(rng.normal(80, 20, (200, 24)), index=days, columns=range(24))
    good = actual + rng.normal(0, 5, (200, 24))
    bad = actual + rng.normal(0, 15, (200, 24))
    assert fc.metrics(actual, bad, bad)["rmae"] == pytest.approx(1.0)
    _, p = fc.dm_test(actual, bad, good)
    assert p < 1e-6
    _, p_rev = fc.dm_test(actual, good, bad)
    assert p_rev > 0.99
