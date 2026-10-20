"""Offline tests for v0.3: the battery schedule on hand-solvable price vectors, its physical
constraints, the naive benchmark and the spread statistics."""

import numpy as np
import pandas as pd
import pytest

from deppa import db, storage as st
from test_core import synthetic


def test_lossless_two_hour_arbitrage_by_hand():
    b = st.Battery(energy=1.0, eta_rt=1.0, deg_cost=0.0, soc0=0.0)
    assert st.schedule(np.array([10.0, 100.0]), b)["profit"] == pytest.approx(90.0)


def test_negative_prices_are_charged_without_simultaneous_discharge():
    # 81% round trip (90% each way), empty at midnight: charge 1 MW + 0.111 MW to fill 1 MWh,
    # discharge the 0.9 MWh at zero price; profit = 50 * 1.111 = 55.56
    b = st.Battery(energy=1.0, eta_rt=0.81, deg_cost=0.0, soc0=0.0)
    s = st.schedule(np.array([-50.0, -50.0, 0.0, 0.0]), b)
    assert s["profit"] == pytest.approx(50 / 0.9, rel=1e-6)
    assert np.all(s["charge"] * s["discharge"] == 0)


def test_physical_limits_and_energy_balance():
    rng = np.random.default_rng(3)
    b = st.Battery(energy=2.0)
    p = rng.normal(80, 40, 24)
    s = st.schedule(p, b)
    assert s["charge"].max() <= b.power + 1e-9 and s["discharge"].max() <= b.power + 1e-9
    assert s["soc"].min() >= -1e-9 and s["soc"].max() <= b.energy + 1e-9
    stored = b.eta * s["charge"].sum() - s["discharge"].sum() / b.eta
    assert stored == pytest.approx(0, abs=1e-6)  # ends where it started
    assert s["soc"][-1] == pytest.approx(b.soc0 * b.energy)


def test_flat_prices_give_no_trade_and_degradation_reduces_cycling():
    b = st.Battery()
    assert st.schedule(np.full(24, 70.0), b)["discharge"].sum() == pytest.approx(0)
    p = 60 + 30 * np.sin(np.arange(24) / 24 * 2 * np.pi)
    cheap = st.schedule(p, st.Battery(deg_cost=0.0))["discharge"].sum()
    costly = st.schedule(p, st.Battery(deg_cost=40.0))["discharge"].sum()
    assert costly <= cheap


def test_naive_schedule_never_beats_the_optimum():
    h = db.prepare_hourly(synthetic(24 * 20))
    h["price"] = h["price"] + np.random.default_rng(1).normal(0, 25, len(h))
    days = {d: p for d, p in st.daily_prices(h).items() if len(p) == 24}
    r = st.run_days(days, st.Battery()).dropna()
    assert (r["profit_naive"] <= r["profit"] + 1e-6).all()


def test_spreads_on_a_known_day():
    ts = pd.date_range("2024-06-03 22:00", periods=24, freq="h", tz="UTC")  # local 4 June 00:00-23:00
    price = np.arange(24, dtype=float)
    h = pd.DataFrame({"ts_utc": ts, "price": price, "solar": np.ones(24), "load": np.full(24, 4.0)})
    s = st.spreads(h).iloc[0]
    assert s["spread_maxmin"] == 23 and s["spread_2h"] == pytest.approx(22.5 - 0.5)
    assert s["solar_share"] == pytest.approx(0.25)
