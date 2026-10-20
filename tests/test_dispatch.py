"""Offline tests for v0.4: merit-order dispatch against the equivalent LP (HiGHS duals), block costs,
fleet bounds and the thermal-demand identity."""

import numpy as np
import pandas as pd
import pytest
from scipy.optimize import linprog

from deppa import dispatch as dp, fuels


def _blocks(rng, n=12):
    fuels_ = ["lignite", "hard_coal", "gas"]
    return sorted((float(c), fuels_[i % 3], float(s)) for i, (c, s) in
                  enumerate(zip(rng.uniform(10, 200, n), rng.uniform(100, 2000, n))))


def test_merit_order_price_equals_lp_dual():
    rng = np.random.default_rng(4)
    for _ in range(20):
        blocks = _blocks(rng)
        must = {"lignite": 3000.0, "hard_coal": 500.0, "gas": 1000.0}
        demand = sum(must.values()) + rng.uniform(100, sum(b[2] for b in blocks) - 100)
        price, out = dp.merit_order(demand, must, blocks)
        # LP: min sum c_i x_i  s.t. sum x_i = demand - must-run, 0 <= x_i <= size_i
        c = np.array([b[0] for b in blocks])
        res = linprog(c, A_eq=np.ones((1, len(blocks))), b_eq=[demand - sum(must.values())],
                      bounds=[(0, b[2]) for b in blocks], method="highs")
        assert res.status == 0
        assert price == pytest.approx(res.eqlin.marginals[0], abs=1e-6)
        assert sum(out.values()) == pytest.approx(demand)


def test_must_run_covering_demand_gives_zero_price():
    must = {"lignite": 5000.0, "hard_coal": 0.0, "gas": 1000.0}
    price, out = dp.merit_order(4000.0, must, [(50.0, "gas", 1000.0)])
    assert price == 0.0 and out == must


def test_block_costs_reference_and_order():
    p = pd.Series({"gas_eur_mwh": 30.0, "coal_eur_mwh": 12.0, "co2_eur_t": 80.0})
    c = dp.block_costs(p)
    # best gas plant: (30 + 0.202 * 80) / 0.60 + 2 = 78.8 EUR/MWh
    assert c["gas"][0] == pytest.approx((30 + 0.202 * 80) / 0.60 + 2)
    for f in dp.THERMAL:
        assert np.all(np.diff(c[f]) > 0)  # less efficient blocks cost more


def test_fleet_capacity_and_must_run_bounds():
    rng = np.random.default_rng(0)
    df = pd.DataFrame({"year": 2024, "month": 1, "lignite": rng.uniform(5e3, 15e3, 744),
                       "hard_coal": rng.uniform(0, 8e3, 744), "gas": rng.uniform(2e3, 20e3, 744)})
    fl = dp.fleet(df, q=0.15)
    for _, r in fl.iterrows():
        assert r["must_run"] <= r["capacity"]
        assert r["capacity"] == pytest.approx(df[r["fuel"]].max())


def test_thermal_demand_identity():
    ts = pd.date_range("2024-01-01", periods=3, freq="h", tz="UTC")
    hourly = pd.DataFrame({"ts_utc": ts, "price": [50.0, 60, 70], "load": [60e3, 62e3, 64e3],
                           "wind_onshore": 10e3, "wind_offshore": 2e3, "solar": 0.0})
    gen = pd.DataFrame({"ts_utc": ts, "lignite": 10e3, "hard_coal": 5e3, "gas": 8e3, "nuclear": 0.0,
                        "hydro": 2e3, "other_conv": 1e3, "other_ren": 0.1e3, "biomass": 4e3,
                        "pumped_gen": 1e3, "pumped_cons": 0.5e3})
    df = dp.thermal_demand(hourly, gen)
    assert (df["thermal_demand"] == 23e3).all()
    supply = df[["wind_onshore", "wind_offshore", "solar", "hydro", "biomass", "other_ren", "other_conv",
                 "nuclear", "pumped_gen", "lignite", "hard_coal", "gas", "net_imports"]].sum(axis=1)
    assert np.allclose(supply, df["load"] + df["pumped_cons"])


def test_fuel_unit_conversions():
    # 10 USD/MMBtu at 1.10 USD/EUR = 31.02 EUR/MWh; 100 USD/t coal = 13.03 EUR/MWh thermal
    assert 10 / 1.10 * fuels.MMBTU_PER_MWH == pytest.approx(31.02, abs=0.01)
    assert 100 / 1.10 / fuels.COAL_MWH_PER_T == pytest.approx(13.03, abs=0.01)
