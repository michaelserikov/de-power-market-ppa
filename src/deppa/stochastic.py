"""Battery scheduling under price uncertainty: stochastic programming, EVPI, VSS and CVaR (v0.8).

Decision: the battery fixes tomorrow's hourly charge/discharge schedule before the day-ahead
auction, when prices are still uncertain (self-scheduling without price-dependent bids).
Uncertainty: S price scenarios for the day = point forecast + the 24-hour error vectors of that
forecast on the previous S days (keeps the dependence between hours).

Measures (Birge and Louveaux), for an objective f(schedule, scenario prices):
- WS  (wait and see): mean over scenarios of the optimal profit when the scenario is known;
- RP  (recourse problem / stochastic solution): best schedule for the scenario set;
- EEV: the schedule optimised on the mean scenario, evaluated over the scenarios;
- EVPI = WS - RP, VSS = RP - EEV.
With a risk-neutral objective the profit is linear in the prices and the constraints do not
depend on them, so the stochastic solution equals the mean-price solution and VSS = 0. With a
risk-averse objective (1 - lam) E[profit] + lam CVaR_alpha[profit], CVaR being the mean profit of
the worst alpha share of scenarios (Rockafellar-Uryasev linearisation), the scenario spread matters
and VSS can be positive.
"""

from __future__ import annotations

import numpy as np
import pandas as pd
from scipy.optimize import Bounds, LinearConstraint, milp

from .storage import Battery


def schedule_risk(scen: np.ndarray, b: Battery, lam: float = 0.0, alpha: float = 0.1) -> dict:
    """Best common schedule for scenario prices `scen` (S x T) under (1-lam) E + lam CVaR_alpha.

    Variables: c, d, s, u (T each) as in storage.schedule, then eta and z_1..z_S for CVaR.
    """
    scen = np.atleast_2d(np.asarray(scen, float))
    S, T = scen.shape
    ic, id_, is_, iu, ie, iz = 0, T, 2 * T, 3 * T, 4 * T, 4 * T + 1
    n = 4 * T + 1 + S
    pbar = scen.mean(axis=0)
    cost = np.zeros(n)                                   # milp minimises: -objective
    cost[ic:ic + T] = (1 - lam) * pbar
    cost[id_:id_ + T] = -(1 - lam) * pbar + (1 - lam) * b.deg_cost
    cost[ie] = -lam
    cost[iz:iz + S] = lam / (alpha * S)

    rows, lo, hi = [], [], []
    s0 = b.soc0 * b.energy
    for t in range(T):
        r = np.zeros(n); r[is_ + t] = 1.0
        if t > 0:
            r[is_ + t - 1] = -1.0
        r[ic + t] = -b.eta; r[id_ + t] = 1.0 / b.eta
        rows.append(r); v = s0 if t == 0 else 0.0; lo.append(v); hi.append(v)
    r = np.zeros(n); r[is_ + T - 1] = 1.0; rows.append(r); lo.append(s0); hi.append(s0)
    for t in range(T):
        r = np.zeros(n); r[ic + t] = 1.0; r[iu + t] = -b.power; rows.append(r); lo.append(-np.inf); hi.append(0.0)
        r = np.zeros(n); r[id_ + t] = 1.0; r[iu + t] = b.power; rows.append(r); lo.append(-np.inf); hi.append(b.power)
    if lam > 0:
        for k in range(S):                               # z_k >= eta - profit_k
            r = np.zeros(n)
            r[iz + k] = 1.0; r[ie] = -1.0
            r[ic:ic + T] = -scen[k]
            r[id_:id_ + T] = scen[k] - b.deg_cost
            rows.append(r); lo.append(0.0); hi.append(np.inf)

    lb = np.r_[np.zeros(4 * T), -np.inf, np.zeros(S)]
    ub = np.r_[np.full(2 * T, b.power), np.full(T, b.energy), np.ones(T), np.inf, np.full(S, np.inf)]
    if lam == 0:                                          # CVaR variables unused: pin them
        lb[ie:] = 0.0; ub[ie:] = 0.0
    integrality = np.r_[np.zeros(3 * T), np.ones(T), np.zeros(1 + S)]
    res = milp(cost, constraints=LinearConstraint(np.array(rows), lo, hi),
               bounds=Bounds(lb, ub), integrality=integrality)
    if not res.success:
        raise RuntimeError(res.message)
    x = res.x
    c, d = np.clip(x[ic:ic + T], 0, None), np.clip(x[id_:id_ + T], 0, None)
    return {"charge": c, "discharge": d, "objective": float(-res.fun)}


def profits(scen: np.ndarray, charge: np.ndarray, discharge: np.ndarray, b: Battery) -> np.ndarray:
    """Profit of one schedule in each scenario."""
    return np.atleast_2d(scen) @ (discharge - charge) - b.deg_cost * discharge.sum()


def objective(pi: np.ndarray, lam: float, alpha: float = 0.1) -> float:
    """(1 - lam) mean + lam CVaR_alpha (mean of the worst alpha share; fractional tail weight)."""
    srt = np.sort(pi)
    m = alpha * len(pi)
    k = int(np.floor(m))
    tail = srt[:k].sum() + (m - k) * (srt[k] if k < len(pi) else 0.0)
    return float((1 - lam) * pi.mean() + lam * tail / m)


def day_measures(scen: np.ndarray, actual: np.ndarray, b: Battery, lams=(0.0, 0.5, 1.0), alpha: float = 0.1) -> dict:
    """WS, RP, EEV, EVPI and VSS for each risk weight, plus the realised profit of each schedule."""
    ev = schedule_risk(scen.mean(axis=0)[None, :], b)               # expected-value schedule
    pi_ev = profits(scen, ev["charge"], ev["discharge"], b)
    ws_pi = np.array([schedule_risk(s[None, :], b)["objective"] for s in scen])
    out = {"realised_ev": float(profits(actual, ev["charge"], ev["discharge"], b)[0]),
           "realised_perfect": float(schedule_risk(actual[None, :], b)["objective"])}
    for lam in lams:
        rp = schedule_risk(scen, b, lam, alpha)
        pi_rp = profits(scen, rp["charge"], rp["discharge"], b)
        rp_val, eev = objective(pi_rp, lam, alpha), objective(pi_ev, lam, alpha)
        ws = objective(ws_pi, lam, alpha)
        out[f"lam{lam}"] = {"ws": ws, "rp": rp_val, "eev": eev, "evpi": ws - rp_val, "vss": rp_val - eev,
                            "expected": float(pi_rp.mean()), "cvar": objective(pi_rp, 1.0, alpha),
                            "realised": float(profits(actual, rp["charge"], rp["discharge"], b)[0]),
                            "discharged": float(rp["discharge"].sum())}
    return out


def error_scenarios(actual: pd.DataFrame, point: pd.DataFrame, day: pd.Timestamp, n: int = 182) -> np.ndarray:
    """Point forecast for `day` plus the error vectors of the previous n days (n x 24)."""
    past = pd.date_range(day - pd.Timedelta(days=n), day - pd.Timedelta(days=1), freq="D")
    err = (actual.loc[past] - point.loc[past]).to_numpy()
    return point.loc[day].to_numpy()[None, :] + err
