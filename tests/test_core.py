"""Offline tests on synthetic data: SMARD parsing, local calendar, SQL and pandas capture prices, PPA identities."""

import numpy as np
import pandas as pd
import pytest

from deppa import db, ppa
from deppa.smard import parse_chunk


def synthetic(hours: int = 24 * 70, seed: int = 1) -> pd.DataFrame:
    rng = np.random.default_rng(seed)
    ts = pd.date_range("2023-12-31 23:00", periods=hours, freq="h", tz="UTC")
    hour = ts.tz_convert("Europe/Berlin").hour.to_numpy()
    solar = np.clip(np.sin((hour - 6) / 12 * np.pi), 0, None) * 1000
    wind = rng.uniform(100, 900, hours)
    price = 90 - 0.06 * solar + rng.normal(0, 10, hours)  # solar depresses prices
    return pd.DataFrame({"ts_utc": ts, "price": price, "wind_onshore": wind, "wind_offshore": wind / 3,
                         "solar": solar, "load": np.full(hours, 5000.0)})


def test_parse_chunk_drops_nulls_and_keeps_utc():
    df = parse_chunk({"series": [[1704063600000, 50.0], [1704067200000, None]]})
    assert len(df) == 1
    assert str(df["ts_utc"].dt.tz) == "UTC"
    assert df["ts_utc"].iloc[0] == pd.Timestamp("2023-12-31 23:00", tz="UTC")


def test_local_calendar_puts_utc_2300_on_new_year():
    h = db.prepare_hourly(synthetic(48))
    assert (h.loc[0, "year"], h.loc[0, "month"], h.loc[0, "hour_local"]) == (2024, 1, 0)


def test_sql_capture_price_matches_pandas():
    h = db.prepare_hourly(synthetic())
    con = db.connect(h)
    by_year = db.capture_prices(con, "year").set_index("tech")
    for tech in ppa.TECHS:
        assert by_year.loc[tech, "capture_price"] == pytest.approx(ppa.capture_price(h["price"], h[tech]))
    assert by_year.loc["solar", "capture_rate"] < by_year.loc["wind_onshore", "capture_rate"]


def test_flat_profile_has_capture_rate_one():
    h = db.prepare_hourly(synthetic())
    h["wind_onshore"] = 1.0
    cp = ppa.capture_price(h["price"], h["wind_onshore"])
    assert cp == pytest.approx(h["price"].mean())


def test_fair_strike_makes_pooled_offtaker_result_zero():
    h = db.prepare_hourly(synthetic())
    k = ppa.fair_pap_strike(h, "solar")
    m = ppa.pap_monthly_result(h, "solar", k)
    weighted = (m["offtaker_eur_per_mwh"] * m["generation_mwh"]).sum() / m["generation_mwh"].sum()
    assert weighted == pytest.approx(0, abs=1e-9)


def test_profile_cost_equals_baseload_minus_capture():
    h = db.prepare_hourly(synthetic())
    row = ppa.baseload_profile_cost(h, "solar").iloc[0]
    assert row["profile_cost"] == pytest.approx(row["baseload_price"] - row["capture_price"])
    assert row["profile_cost"] > 0  # the synthetic solar profile coincides with low prices


def test_missing_generation_hours_are_skipped():
    h = db.prepare_hourly(synthetic())
    h.loc[:10, "solar"] = np.nan
    assert np.isfinite(ppa.capture_price(h["price"], h["solar"]))
