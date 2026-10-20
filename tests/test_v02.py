"""Offline tests for v0.2: option formulas against references and Monte Carlo, the two-factor
challenger, VaR backtests on cases with known answers, GARCH estimation and the PPA P&L."""

import numpy as np
import pandas as pd
import pytest

from deppa import db, risk, valuation as val
from test_core import synthetic


# --- Valuation -------------------------------------------------------------------------------

def test_black76_atm_reference_value_and_parity():
    # ATM, r = 0: price = F * (2 N(sigma sqrt(T) / 2) - 1) = 7.9656 for F = 100, sigma = 0.2, T = 1
    assert val.black76(100, 100, 1.0, 0.2, 0.0, "call") == pytest.approx(7.965567, abs=1e-6)
    c = val.black76(90, 80, 0.7, 0.5, 0.03, "call")
    p = val.black76(90, 80, 0.7, 0.5, 0.03, "put")
    assert c - p == pytest.approx(np.exp(-0.03 * 0.7) * (90 - 80), abs=1e-12)


def test_mc_replicates_black76_within_four_standard_errors():
    for K in (60, 90, 120):
        b = val.black76(90, K, 0.5, 0.5, 0.02)
        mc, se = val.mc_black76(90, K, 0.5, 0.5, 0.02, n=200_000, seed=K)
        assert abs(mc - b) < 4 * se


def test_analytic_greeks_match_finite_differences():
    a = val.black76_greeks(85, 70, 0.6, 0.45, 0.02)
    b = val.bump_greeks(85, 70, 0.6, 0.45, 0.02)
    for g in a:
        assert a[g] == pytest.approx(b[g], rel=1e-5)


def test_implied_vol_round_trip():
    price = val.black76(85, 70, 0.6, 0.45, 0.02)
    assert val.implied_vol(price, 85, 70, 0.6, 0.02) == pytest.approx(0.45, abs=1e-8)


def test_two_factor_average_std_and_put_match_monte_carlo():
    p = val.TwoFactorParams(phi=0.5, sigma_short=20.0, sigma_level=2.0, weekday=np.zeros(7))
    start, m0 = pd.Timestamp("2025-12-31"), pd.Timestamp("2026-03-01")
    sd = val.average_std(p, (m0 - start).days - 1, 31)
    analytic = val.bachelier_put(90, 70, sd)
    mc, se = val.mc_average_put(90, 70, p, start, m0, n=100_000, seed=3)
    assert abs(mc - analytic) < 4 * se


def test_two_factor_calibration_recovers_ar1_coefficient():
    rng = np.random.default_rng(5)
    n = 3000
    x = np.zeros(n)
    for i in range(1, n):
        x[i] = 0.6 * x[i - 1] + 15 * rng.standard_normal()
    idx = pd.date_range("2015-01-01", periods=n, freq="D")
    wd = np.array([5, 8, 9, 7, 3, -12, -20], float)
    price = pd.Series(80 + wd[idx.dayofweek] + x, index=idx)
    p = val.calibrate_two_factor(price)
    # Removing the 28-day centred mean biases phi down by about 0.07 (documented in the report)
    assert 0.5 < p.phi < 0.6
    assert p.weekday[6] < p.weekday[2]


# --- Backtests -------------------------------------------------------------------------------

def test_traffic_light_reproduces_basel_bands():
    zones = [risk.traffic_light(x) for x in (0, 4, 5, 9, 10)]
    assert zones == ["green", "green", "yellow", "yellow", "red"]


def test_kupiec_is_zero_at_expected_rate_and_rejects_far_too_many():
    hits = np.zeros(1000, bool)
    hits[:10] = True
    lr, p = risk.kupiec_pof(hits, 0.01)
    assert lr == pytest.approx(0, abs=1e-9) and p == pytest.approx(1)
    hits[:40] = True
    assert risk.kupiec_pof(hits, 0.01)[1] < 1e-6


def test_christoffersen_detects_clustered_exceptions():
    spread = np.zeros(1000, bool)
    spread[::100] = True
    clustered = np.zeros(1000, bool)
    clustered[500:510] = True
    assert risk.christoffersen(spread, 0.01)["p_ind"] > 0.5
    assert risk.christoffersen(clustered, 0.01)["p_ind"] < 1e-6


def test_garch_t_recovers_persistence():
    rng = np.random.default_rng(2)
    n, w, a, b, nu = 4000, 0.05, 0.10, 0.85, 6.0
    h, x = 1.0, np.empty(n)
    for i in range(n):
        x[i] = np.sqrt(h) * rng.standard_t(nu) * np.sqrt((nu - 2) / nu)
        h = w + a * x[i] ** 2 + b * h
    fit = risk.fit_garch_t(x)
    assert fit["alpha"] + fit["beta"] == pytest.approx(a + b, abs=0.05)
    assert 3 < fit["nu"] < 15


def test_hs_and_parametric_var_es_ordering():
    x = np.random.default_rng(0).standard_normal(100_000)
    var, es = risk.hs_var_es(x, 0.99, 0.975)
    assert var == pytest.approx(2.326, abs=0.05) and es == pytest.approx(2.338, abs=0.05)
    nv, ne = risk.normal_var_es(0, 1, 0.99, 0.975)
    tv, te = risk.t_var_es(0, 1, 1e6, 0.99, 0.975)  # t with huge nu is normal
    assert (nv, ne) == pytest.approx((tv, te), abs=1e-3)


# --- PPA P&L ---------------------------------------------------------------------------------

def test_daily_pnl_scales_volume_and_is_zero_at_flat_price():
    h = db.prepare_hourly(synthetic())
    h = h[h["year"] == 2024]
    h["price"] = 50.0
    assert risk.daily_pnl(h, "solar", 50.0).abs().max() == pytest.approx(0, abs=1e-6)
    h["price"] = 51.0
    assert risk.daily_pnl(h, "solar", 50.0, annual_mwh=1000).sum() == pytest.approx(1000)


def test_off_days_include_moving_holidays():
    d = pd.DatetimeIndex(["2025-04-18", "2025-04-22", "2025-06-09", "2025-10-03", "2025-10-04"])
    assert risk.is_off_day(d).tolist() == [True, False, True, True, True]
