"""Run the v0.1 pipeline: download (cached), build the DuckDB table, compute results, draw figures.

    python -m deppa.run                # 2023-2025
    python -m deppa.run --start 2023-01-01 --end 2025-12-31
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

import pandas as pd

from . import db, plots, ppa
from .smard import load_all

ROOT = Path(__file__).resolve().parents[2]


def main(argv: list[str] | None = None) -> dict:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--start", default="2023-01-01")
    ap.add_argument("--end", default="2025-12-31")
    args = ap.parse_args(argv)

    data, results, figures = ROOT / "data", ROOT / "results", ROOT / "figures"
    for d in (data, results, figures):
        d.mkdir(exist_ok=True)

    # Download one extra UTC day before the start: local midnight on 1 January is 23:00 UTC.
    first_day = (pd.Timestamp(args.start) - pd.Timedelta(days=1)).date().isoformat()
    raw = load_all(first_day, args.end, data / "raw")
    hourly = db.prepare_hourly(raw)
    # Local-calendar filter: the UTC download window is a day wider than the local years.
    years = range(pd.Timestamp(args.start).year, pd.Timestamp(args.end).year + 1)
    hourly = hourly[hourly["year"].isin(years)].reset_index(drop=True)

    con = db.connect(hourly, data / "market.duckdb")
    yearly = db.capture_prices(con, "year")
    monthly_sql = db.capture_prices(con, "year, month")
    yearly.to_csv(results / "capture_prices_yearly.csv", index=False, float_format="%.4f")
    monthly_sql.to_csv(results / "capture_prices_monthly.csv", index=False, float_format="%.4f")

    summary: dict = {"period": [args.start, args.end], "hours": int(len(hourly)),
                     "hours_missing_generation": {t: int(hourly[t].isna().sum()) for t in ppa.TECHS}}
    monthly, pap, profile = {}, {}, []
    for tech in ppa.TECHS:
        monthly[tech] = ppa.monthly_capture(hourly, tech)
        strike = ppa.fair_pap_strike(hourly, tech)
        pap[tech] = ppa.pap_monthly_result(hourly, tech, strike)
        yearly_strikes = {int(y): ppa.capture_price(df["price"], df[tech]) for y, df in hourly.groupby("year")}
        summary[tech] = {
            "fair_pap_strike_pooled": strike,
            "fair_pap_strike_by_year": yearly_strikes,
            "offtaker_monthly_eur_per_mwh": ppa.risk_summary(pap[tech]["offtaker_eur_per_mwh"]),
        }
        profile.append(ppa.baseload_profile_cost(hourly, tech))
    profile_df = pd.concat(profile, ignore_index=True)
    profile_df.to_csv(results / "baseload_profile_cost.csv", index=False, float_format="%.4f")
    pd.concat([m.assign(tech=t) for t, m in pap.items()]).to_csv(
        results / "pap_monthly_offtaker.csv", index=False, float_format="%.4f")

    slope, intercept = ppa.cannibalisation_slope(monthly["solar"])
    summary["solar_cannibalisation"] = {"slope_capture_rate_per_unit_share": slope, "intercept": intercept}
    (results / "summary.json").write_text(json.dumps(summary, indent=2), encoding="utf-8")

    plots.capture_rates(yearly, figures / "capture_rates.png")
    plots.monthly_prices(monthly, figures / "monthly_prices.png")
    plots.cannibalisation(monthly["solar"], slope, intercept, figures / "solar_cannibalisation.png")
    plots.pap_risk(pap, figures / "pap_offtaker_risk.png")
    con.close()
    return summary


if __name__ == "__main__":
    main()
