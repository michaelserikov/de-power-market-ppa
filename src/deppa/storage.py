"""Day-ahead arbitrage of a battery (BESS) on the German market, and the price spreads it lives on.

The battery has 1 MW of power and 1, 2 or 4 MWh of energy. For every local day it buys and sells
at the day-ahead prices of that day, which are known the day before delivery, so a schedule
optimised on them is achievable in practice (no intraday, balancing or ancillary revenues here).

Per day the schedule is a small mixed-integer linear program:
    max  sum_t  p_t * (d_t - c_t) - k * d_t
    s.t. s_t = s_{t-1} + eta_c * c_t - d_t / eta_d,     0 <= s_t <= E,  s_0 = s_T = E / 2
         0 <= c_t <= P * u_t,  0 <= d_t <= P * (1 - u_t),  u_t binary
where c and d are charging and discharging power (MW, one-hour steps), s the state of charge
(MWh), k a degradation cost per MWh discharged and u forbids charging and discharging in the
same hour (otherwise negative prices would reward burning energy through the losses).

Benchmark for the value of information: a naive schedule optimised on yesterday's prices and
settled at today's prices.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd
from scipy.optimize import Bounds, LinearConstraint, milp


@dataclass(frozen=True)
class Battery:
    power: float = 1.0          # MW
    energy: float = 2.0         # MWh
    eta_rt: float = 0.88        # round-trip efficiency, split equally on charge and discharge
    deg_cost: float = 10.0      # EUR per MWh discharged
    soc0: float = 0.5           # state of charge at the start and end of each day, share of energy

    @property
    def eta(self) -> float:
        return float(np.sqrt(self.eta_rt))


def schedule(prices: np.ndarray, b: Battery) -> dict:
    """Optimal one-day schedule for the given hourly prices. Returns charge, discharge, soc and profit."""
    p = np.asarray(prices, float)
    T = len(p)
    # variable order: c (T), d (T), s (T), u (T)
    n = 4 * T
    ic, id_, is_, iu = 0, T, 2 * T, 3 * T
    cost = np.zeros(n)
    cost[ic:ic + T] = p
    cost[id_:id_ + T] = -p + b.deg_cost

    rows, lo, hi = [], [], []
    s0 = b.soc0 * b.energy
    for t in range(T):  # s_t - s_{t-1} - eta c_t + d_t / eta = 0
        r = np.zeros(n)
        r[is_ + t] = 1.0
        if t > 0:
            r[is_ + t - 1] = -1.0
        r[ic + t] = -b.eta
        r[id_ + t] = 1.0 / b.eta
        rows.append(r)
        rhs = s0 if t == 0 else 0.0
        lo.append(rhs); hi.append(rhs)
    r = np.zeros(n); r[is_ + T - 1] = 1.0  # end-of-day state of charge
    rows.append(r); lo.append(s0); hi.append(s0)
    for t in range(T):  # c_t <= P u_t ;  d_t <= P (1 - u_t)
        r = np.zeros(n); r[ic + t] = 1.0; r[iu + t] = -b.power
        rows.append(r); lo.append(-np.inf); hi.append(0.0)
        r = np.zeros(n); r[id_ + t] = 1.0; r[iu + t] = b.power
        rows.append(r); lo.append(-np.inf); hi.append(b.power)

    ub = np.r_[np.full(2 * T, b.power), np.full(T, b.energy), np.ones(T)]
    integrality = np.r_[np.zeros(3 * T), np.ones(T)]
    res = milp(cost, constraints=LinearConstraint(np.array(rows), lo, hi),
               bounds=Bounds(np.zeros(n), ub), integrality=integrality)
    if not res.success:
        raise RuntimeError(f"battery schedule infeasible: {res.message}")
    x = res.x
    c, d, s = x[ic:ic + T], x[id_:id_ + T], x[is_:is_ + T]
    c[c < 1e-9] = 0.0
    d[d < 1e-9] = 0.0
    return {"charge": c, "discharge": d, "soc": s,
            "profit": float(p @ (d - c) - b.deg_cost * d.sum())}


def settle(prices: np.ndarray, charge: np.ndarray, discharge: np.ndarray, b: Battery) -> float:
    """Profit of a given schedule at the given prices (net of degradation cost)."""
    p = np.asarray(prices, float)
    return float(p @ (discharge - charge) - b.deg_cost * discharge.sum())


def daily_prices(hourly: pd.DataFrame) -> dict:
    """Hourly price vectors per local calendar day (23 or 25 hours on clock-change days)."""
    local = hourly["ts_utc"].dt.tz_convert("Europe/Berlin")
    day = local.dt.tz_localize(None).dt.normalize()
    return {d: g.to_numpy() for d, g in hourly["price"].groupby(day)}


def run_days(days: dict, b: Battery, naive: bool = True) -> pd.DataFrame:
    """Optimal (and optionally naive, yesterday's-price) schedules for every day."""
    rows, prev = [], None
    for day, p in days.items():
        opt = schedule(p, b)
        row = {"date": day, "hours": len(p), "profit": opt["profit"],
               "discharged_mwh": float(opt["discharge"].sum()),
               "charged_mwh": float(opt["charge"].sum()),
               "charge_at_negative_mwh": float(opt["charge"][p < 0].sum())}
        if naive:
            if prev is not None and len(prev) == len(p):
                nv = schedule(prev, b)
                row["profit_naive"] = settle(p, nv["charge"], nv["discharge"], b)
            else:  # clock-change days and the first day: no comparable yesterday, use the optimum
                row["profit_naive"] = np.nan
        rows.append(row)
        prev = p
    return pd.DataFrame(rows)


def hourly_profile(days: dict, b: Battery) -> pd.DataFrame:
    """Mean net discharge (MW, discharge minus charge) by local hour and year, for 24-hour days."""
    rows = []
    for day, p in days.items():
        if len(p) != 24:
            continue
        s = schedule(p, b)
        for h in range(24):
            rows.append({"year": day.year, "hour": h, "net_mw": s["discharge"][h] - s["charge"][h]})
    return pd.DataFrame(rows).groupby(["year", "hour"])["net_mw"].mean().unstack(0)


def spreads(hourly: pd.DataFrame) -> pd.DataFrame:
    """Per local day: max-min price spread, mean of the 2 highest minus the 2 lowest hours, solar share of load."""
    df = hourly.copy()
    df["day"] = df["ts_utc"].dt.tz_convert("Europe/Berlin").dt.tz_localize(None).dt.normalize()

    def agg(g: pd.DataFrame) -> pd.Series:
        p = np.sort(g["price"].to_numpy())
        return pd.Series({"spread_maxmin": p[-1] - p[0], "spread_2h": p[-2:].mean() - p[:2].mean(),
                          "solar_share": g["solar"].sum() / g["load"].sum(),
                          "negative_hours": int((g["price"] < 0).sum())})

    return df.groupby("day")[["price", "solar", "load"]].apply(agg)


def summarise(results: dict[float, pd.DataFrame]) -> pd.DataFrame:
    """Per duration and year: profit per MW, cycles, value of perfect day-ahead information vs naive."""
    rows = []
    for energy, r in results.items():
        r = r.assign(year=pd.to_datetime(r["date"]).dt.year)
        for year, g in r.groupby("year"):
            ok = g["profit_naive"].notna()
            rows.append({
                "duration_h": energy, "year": year,
                "profit_eur_per_mw": g["profit"].sum(),
                "cycles": g["discharged_mwh"].sum() / energy,
                "share_charged_at_negative_price": g["charge_at_negative_mwh"].sum() / g["charged_mwh"].sum(),
                "naive_capture": g.loc[ok, "profit_naive"].sum() / g.loc[ok, "profit"].sum(),
            })
    return pd.DataFrame(rows)
