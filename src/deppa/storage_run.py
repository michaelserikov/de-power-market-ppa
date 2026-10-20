"""Run the v0.3 battery module: day-ahead arbitrage of 1, 2 and 4-hour batteries, 2023-2025.

    python -m deppa.storage_run       # uses the cached SMARD data (downloads if missing), ~8 minutes

Writes CSV/JSON to results/storage/ and figures to figures/.
"""

from __future__ import annotations

import argparse
import json

import numpy as np
import pandas as pd

from . import plots, storage as st
from .run import ROOT, load_hourly

DURATIONS = (1.0, 2.0, 4.0)       # hours of storage at 1 MW
DEG_COSTS = (0.0, 10.0, 20.0)     # EUR per MWh discharged; 10 is the base case
BASE = st.Battery()               # 1 MW / 2 MWh, 88% round trip, 10 EUR/MWh, half full at midnight


def main(argv: list[str] | None = None) -> dict:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--start", default="2023-01-01")
    ap.add_argument("--end", default="2025-12-31")
    args = ap.parse_args(argv)
    out, figures = ROOT / "results" / "storage", ROOT / "figures"
    out.mkdir(parents=True, exist_ok=True)

    hourly = load_hourly(args.start, args.end)
    days = st.daily_prices(hourly)

    results = {}
    for e in DURATIONS:
        b = st.Battery(energy=e)
        results[e] = st.run_days(days, b)
        results[e].to_csv(out / f"daily_{e:.0f}h.csv", index=False, float_format="%.3f")
    summary = st.summarise(results)
    summary.to_csv(out / "summary.csv", index=False, float_format="%.4f")

    deg = []
    for k in DEG_COSTS:
        r = results[2.0] if k == BASE.deg_cost else st.run_days(days, st.Battery(deg_cost=k), naive=False)
        r = r.assign(year=pd.to_datetime(r["date"]).dt.year)
        for year, g in r.groupby("year"):
            deg.append({"deg_cost": k, "year": year, "profit_eur_per_mw": g["profit"].sum(),
                        "cycles": g["discharged_mwh"].sum() / 2.0})
    deg = pd.DataFrame(deg)
    deg.to_csv(out / "degradation_sensitivity_2h.csv", index=False, float_format="%.3f")

    profile = st.hourly_profile(days, BASE)
    profile.to_csv(out / "hourly_profile_2h.csv", float_format="%.4f")

    sp = st.spreads(hourly)
    sp.to_csv(out / "spreads_daily.csv", float_format="%.3f")
    monthly = sp.groupby([sp.index.year, sp.index.month]).mean()
    slope, intercept = np.polyfit(monthly["solar_share"], monthly["spread_2h"], 1)
    by_year = sp.groupby(sp.index.year).agg(spread_maxmin=("spread_maxmin", "mean"),
                                            spread_2h=("spread_2h", "mean"),
                                            negative_hours=("negative_hours", "sum"))

    res = {
        "battery": {"power_mw": BASE.power, "round_trip": BASE.eta_rt, "deg_cost_base": BASE.deg_cost,
                    "soc_start_end": BASE.soc0},
        "summary": summary.round(4).to_dict(orient="records"),
        "degradation_sensitivity_2h": deg.round(2).to_dict(orient="records"),
        "spreads_by_year": by_year.round(2).reset_index().rename(columns={"day": "year"}).to_dict(orient="records"),
        "spread_vs_solar_monthly": {"slope_eur_per_unit_share": float(slope), "intercept": float(intercept),
                                    "months": int(len(monthly))},
    }
    (out / "summary.json").write_text(json.dumps(res, indent=2, default=str), encoding="utf-8")

    plots.storage_revenue(summary, figures / "storage_revenue.png")
    plots.storage_profile(profile, figures / "storage_profile.png")
    plots.spreads_solar(monthly, slope, intercept, figures / "spreads_solar.png")
    return res


if __name__ == "__main__":
    main()
