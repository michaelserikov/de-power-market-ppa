"""Offline tests for v0.8: the stochastic schedule against the deterministic one, the ordering
WS >= RP >= EEV, VSS = 0 for a risk-neutral battery, the CVaR objective and the scenarios."""

import numpy as np
import pandas as pd
import pytest

from deppa import stochastic as sp, storage as st


def _scenarios(seed=0, S=60):
    rng = np.random.default_rng(seed)
    base = 70 + 40 * np.sin((np.arange(24) - 7) / 24 * 2 * np.pi)
    return base[None, :] + rng.normal(0, 25, (S, 24)) + rng.normal(0, 30, (S, 1))


def test_single_scenario_matches_deterministic_battery():
    p = _scenarios()[0]
    b = st.Battery()
    assert sp.schedule_risk(p[None, :], b)["objective"] == pytest.approx(st.schedule(p, b)["profit"], abs=1e-6)


def test_risk_neutral_vss_is_zero_and_ws_rp_eev_are_ordered():
    scen = _scenarios(1)
    m = sp.day_measures(scen, scen[0], st.Battery(), lams=(0.0, 0.5, 1.0))
    assert m["lam0.0"]["vss"] == pytest.approx(0.0, abs=1e-6)
    for lam in ("lam0.0", "lam0.5", "lam1.0"):
        assert m[lam]["ws"] >= m[lam]["rp"] - 1e-6 >= m[lam]["eev"] - 2e-6
        assert m[lam]["evpi"] >= -1e-6 and m[lam]["vss"] >= -1e-6


def test_cvar_objective_and_risk_aversion_trade_off():
    pi = np.arange(1.0, 11.0)                       # 10 scenarios
    assert sp.objective(pi, 1.0, 0.2) == pytest.approx(1.5)   # mean of the worst two
    assert sp.objective(pi, 0.0, 0.2) == pytest.approx(5.5)
    scen = _scenarios(2)
    b = st.Battery()
    neutral = sp.schedule_risk(scen, b, 0.0)
    averse = sp.schedule_risk(scen, b, 1.0, 0.1)
    pn, pa = sp.profits(scen, neutral["charge"], neutral["discharge"], b), sp.profits(scen, averse["charge"], averse["discharge"], b)
    assert pa.mean() <= pn.mean() + 1e-6                              # risk aversion costs expected profit ...
    assert sp.objective(pa, 1.0, 0.1) >= sp.objective(pn, 1.0, 0.1) - 1e-6   # ... and buys a better tail
    assert averse["objective"] == pytest.approx(sp.objective(pa, 1.0, 0.1), rel=1e-6)


def test_error_scenarios_are_point_plus_past_errors():
    days = pd.date_range("2024-01-01", periods=10, freq="D")
    actual = pd.DataFrame(np.arange(240.0).reshape(10, 24), index=days, columns=range(24))
    point = actual - 5.0
    sc = sp.error_scenarios(actual, point, days[-1], n=3)
    assert sc.shape == (3, 24)
    assert np.allclose(sc, point.loc[days[-1]].to_numpy()[None, :] + 5.0)
