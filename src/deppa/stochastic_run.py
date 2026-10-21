"""Run v0.8: battery scheduling under price uncertainty, July 2024 to December 2025.

    python -m deppa.stochastic_run      # needs the v0.5 forecasts; parallel over days, ~10-20 minutes

Writes results/stochastic/ and figures/.
"""

from __future__ import annotations

import json
import os
from concurrent.futures import ProcessPoolExecutor

import numpy as np
import pandas as pd

from . import plots, stochastic as sp, storage as st
from .probabilistic_run import _read
from .run import ROOT

START = "2024-07-01"
LAMS = (0.0, 0.25, 0.5, 0.75, 1.0)
ALPHA = 0.1
SRC = ROOT / "results" / "forecast"


def _one(day: str) -> dict:
    actual = _read(SRC / "actual.csv")
    point = _read(SRC / "forecast_lear_gbm_avg.csv")
    d = pd.Timestamp(day)
    scen = sp.error_scenarios(actual, point, d)
    m = sp.day_measures(scen, actual.loc[d].to_numpy(), st.Battery(), LAMS, ALPHA)
    row = {"date": day, "realised_ev": m["realised_ev"], "realised_perfect": m["realised_perfect"]}
    for lam in LAMS:
        for k, v in m[f"lam{lam}"].items():
            row[f"{k}_{lam}"] = v
    return row


def main() -> dict:
    out, figs = ROOT / "results" / "stochastic", ROOT / "figures"
    out.mkdir(parents=True, exist_ok=True)
    days = [str(d.date()) for d in _read(SRC / "actual.csv").loc[START:].index]
    with ProcessPoolExecutor(max_workers=max(1, (os.cpu_count() or 2) - 1)) as ex:
        rows = list(ex.map(_one, days, chunksize=8))
    df = pd.DataFrame(rows).set_index("date")
    df.index = pd.to_datetime(df.index)
    df.to_csv(out / "daily.csv", float_format="%.3f")

    summ = []
    for lam in LAMS:
        real = df[f"realised_{lam}"]
        summ.append({"lam": lam, "ws": df[f"ws_{lam}"].mean(), "rp": df[f"rp_{lam}"].mean(), "eev": df[f"eev_{lam}"].mean(),
                     "evpi_per_day": df[f"evpi_{lam}"].mean(), "vss_per_day": df[f"vss_{lam}"].mean(),
                     "expected_per_day": df[f"expected_{lam}"].mean(), "cvar_per_day": df[f"cvar_{lam}"].mean(),
                     "realised_per_year": real.mean() * 365, "realised_p05_day": real.quantile(0.05),
                     "realised_worst_day": real.min(), "loss_days": int((real < 0).sum()),
                     "mwh_discharged_per_day": df[f"discharged_{lam}"].mean()})
    summ = pd.DataFrame(summ)
    summ.to_csv(out / "summary_by_lambda.csv", index=False, float_format="%.4f")
    perfect_year = df["realised_perfect"].mean() * 365
    res = {"period": [days[0], days[-1]], "days": len(days), "alpha": ALPHA, "scenarios": 182,
           "perfect_profit_per_year": perfect_year,
           "realised_ev_per_year": df["realised_ev"].mean() * 365,
           "by_lambda": summ.round(3).to_dict(orient="records")}
    (out / "summary.json").write_text(json.dumps(res, indent=2, default=str), encoding="utf-8")

    plots.risk_frontier(summ, figs / "stochastic_frontier.png")
    plots.evpi_vss(summ, figs / "stochastic_evpi_vss.png")
    plots.realised_tail(df, LAMS, figs / "stochastic_realised_tail.png")
    return res


if __name__ == "__main__":
    main()
