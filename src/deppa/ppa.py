"""PPA valuation for wind and solar from hourly prices and generation profiles.

Conventions (EUR/MWh of generation):
- Pay-as-produced (PaP) PPA at strike K: the offtaker takes every MWh produced at K and
  values it at the spot price. Offtaker result per MWh = capture price - K; the seller
  receives K, so the seller's merchant alternative would have earned the capture price.
- Baseload PPA: the seller sells a flat block at the baseload price and covers the
  difference between block and production at spot. With block volume equal to annual
  production, the seller realises baseload strike + (capture price - mean spot price), so
  the shape (profile) cost is mean spot - capture price, i.e. baseload * (1 - capture rate).
"""

from __future__ import annotations

import numpy as np
import pandas as pd

TECHS = ("wind_onshore", "wind_offshore", "solar")


def capture_price(price: pd.Series, gen: pd.Series) -> float:
    """Generation-weighted mean price; hours with missing generation are skipped."""
    ok = gen.notna() & price.notna()
    return float((price[ok] * gen[ok]).sum() / gen[ok].sum())


def monthly_capture(hourly: pd.DataFrame, tech: str) -> pd.DataFrame:
    """Per local month: baseload price, capture price, capture rate and generation share of load."""
    df = hourly.dropna(subset=[tech])
    g = df.assign(pg=df["price"] * df[tech]).groupby(["year", "month"])
    out = pd.DataFrame({
        "baseload_price": g["price"].mean(),
        "capture_price": g["pg"].sum() / g[tech].sum(),
        "generation_mwh": g[tech].sum(),
        "share_of_load": g[tech].sum() / g["load"].sum(),
    }).reset_index()
    out["capture_rate"] = out["capture_price"] / out["baseload_price"]
    return out


def fair_pap_strike(hourly: pd.DataFrame, tech: str) -> float:
    """Pay-as-produced strike at which the offtaker breaks even over the sample (= capture price)."""
    return capture_price(hourly["price"], hourly[tech])


def pap_monthly_result(hourly: pd.DataFrame, tech: str, strike: float) -> pd.DataFrame:
    """Offtaker result per MWh and in EUR per GWh of generation, by month, for a PaP PPA at `strike`."""
    m = monthly_capture(hourly, tech)
    m["offtaker_eur_per_mwh"] = m["capture_price"] - strike
    return m


def risk_summary(values: pd.Series) -> dict:
    """P10 / P50 / P90, mean and worst value of a series."""
    v = values.dropna().to_numpy()
    return {
        "p10": float(np.percentile(v, 10)),
        "p50": float(np.percentile(v, 50)),
        "p90": float(np.percentile(v, 90)),
        "mean": float(v.mean()),
        "worst": float(v.min()),
    }


def baseload_profile_cost(hourly: pd.DataFrame, tech: str) -> pd.DataFrame:
    """Per year: mean spot price, capture price and the shape cost a seller of a baseload PPA bears."""
    rows = []
    for year, df in hourly.groupby("year"):
        cp = capture_price(df["price"], df[tech])
        base = float(df["price"].mean())
        rows.append({"year": year, "tech": tech, "baseload_price": base, "capture_price": cp,
                     "profile_cost": base - cp, "profile_discount": 1 - cp / base})
    return pd.DataFrame(rows)


def cannibalisation_slope(monthly: pd.DataFrame) -> tuple[float, float]:
    """OLS slope and intercept of capture rate on generation share of load (monthly points)."""
    x, y = monthly["share_of_load"].to_numpy(), monthly["capture_rate"].to_numpy()
    slope, intercept = np.polyfit(x, y, 1)
    return float(slope), float(intercept)
