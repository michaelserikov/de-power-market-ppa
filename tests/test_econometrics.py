"""Offline tests for v0.7 on simulated series with known properties."""

import numpy as np
import pandas as pd
import pytest

from deppa import econometrics as ec


def _cointegrated(n=200, seed=0):
    rng = np.random.default_rng(seed)
    gas = 30 + np.cumsum(rng.normal(0, 2, n))
    co2 = 70 + np.cumsum(rng.normal(0, 2, n))
    power = 5 + 1.8 * gas + 0.4 * co2 + rng.normal(0, 2, n)
    idx = pd.period_range("2000-01", periods=n, freq="M")
    return pd.Series(power, idx), pd.Series(gas, idx), pd.Series(co2, idx)


def test_unit_root_tests_separate_random_walk_and_noise():
    power, gas, _ = _cointegrated()
    ur = ec.unit_roots({"gas": gas}).set_index("form")
    assert ur.loc["level", "adf_p"] > 0.05          # random walk: unit root not rejected
    assert ur.loc["difference", "adf_p"] < 0.01     # its differences are stationary


def test_long_run_recovers_pass_through_and_finds_cointegration():
    power, gas, co2 = _cointegrated()
    lr = ec.long_run(power, gas, co2)
    assert lr["b_gas"] == pytest.approx(1.8, abs=0.1) and lr["c_co2"] == pytest.approx(0.4, abs=0.1)
    assert lr["engle_granger_p"] < 0.01 and lr["johansen_rank_95"] >= 1


def test_price_slope_recovers_merit_order_slope():
    rng = np.random.default_rng(1)
    n = 24 * 400
    ts = pd.date_range("2024-01-01", periods=n, freq="h")
    load = rng.uniform(40_000, 70_000, n)
    res = rng.uniform(5_000, 45_000, n)
    month = ts.month
    price = 20 + 2.5 * (load - res) / 1000 + month * 3 + rng.normal(0, 5, n)
    df = pd.DataFrame({"year": ts.year, "month": month, "price": price, "load_fc": load,
                       "onshore_fc": res * 0.5, "offshore_fc": res * 0.1, "solar_fc": res * 0.4})
    s = ec.price_slope(df[df["year"] == 2024])
    assert s[2024]["slope_eur_mwh_per_gw"] == pytest.approx(2.5, abs=0.05)


def test_forecast_error_statistics():
    df = pd.DataFrame({"year": 2024, "wind_onshore": [10.0, 20.0], "wind_offshore": [0.0, 0.0],
                       "onshore_fc": [12.0, 18.0], "offshore_fc": [0.0, 0.0],
                       "solar": [0.0, 10.0], "solar_fc": [0.0, 11.0]})
    e = ec.forecast_errors(df).set_index("tech")
    assert e.loc["wind", "bias_mw"] == pytest.approx(0.0) and e.loc["wind", "mae_mw"] == pytest.approx(2.0)
    assert e.loc["solar", "nmae"] == pytest.approx(0.5 / 5.0)
