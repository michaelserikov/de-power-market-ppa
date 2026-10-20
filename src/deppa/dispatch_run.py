"""Run the v0.4 merit-order dispatch model: calibrate on 2023, validate out of sample on 2024-2025.

    python -m deppa.dispatch_run      # uses cached SMARD, World Bank, ECB and EEX data (downloads if missing)

Two parameters are calibrated on 2023 only, by the hourly price MAE: the mine-mouth lignite fuel
cost and the must-run quantile. 2024 and 2025 are then out of sample. Writes results/dispatch/
and figures/.
"""

from __future__ import annotations

import argparse
import itertools
import json

import pandas as pd

from . import dispatch as dp, fuels, plots, smard
from .run import ROOT, load_hourly

GRID_LIGNITE = (4.0, 8.0, 12.0, 16.0)       # EUR per MWh thermal
GRID_MUST_RUN_Q = (0.05, 0.15, 0.25)
CALIBRATION_YEAR = 2023


def main(argv: list[str] | None = None) -> dict:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--start", default="2023-01-01")
    ap.add_argument("--end", default="2025-12-31")
    args = ap.parse_args(argv)
    data, out, figures = ROOT / "data", ROOT / "results" / "dispatch", ROOT / "figures"
    out.mkdir(parents=True, exist_ok=True)

    hourly = load_hourly(args.start, args.end, data)
    first_day = (pd.Timestamp(args.start) - pd.Timedelta(days=1)).date().isoformat()
    gen = smard.load_fuels(first_day, args.end, data / "raw")
    prices = fuels.monthly_prices(data / "raw" / "fuels", args.start[:7], args.end[:7])
    prices.to_csv(out / "fuel_prices_monthly.csv", float_format="%.3f")
    df = dp.thermal_demand(hourly, gen)

    cal = []
    cal_df = df[df["year"] == CALIBRATION_YEAR]
    for lf, q in itertools.product(GRID_LIGNITE, GRID_MUST_RUN_Q):
        r = dp.run(cal_df, prices, lignite_fuel=lf, must_run_q=q)
        m = dp.metrics(r).iloc[0]
        cal.append({"lignite_fuel": lf, "must_run_q": q, "mae": m["mae"], "bias": m["model_mean"] - m["actual_mean"],
                    "corr_hourly": m["corr_hourly"],
                    "fuel_split_abs_error_pct": dp.generation_check(r)["error_pct"].abs().mean()})
    cal = pd.DataFrame(cal)
    cal.to_csv(out / "calibration_2023.csv", index=False, float_format="%.3f")
    best = cal.loc[cal["mae"].idxmin()]

    res = dp.run(df, prices, lignite_fuel=best["lignite_fuel"], must_run_q=best["must_run_q"])
    met = dp.metrics(res).assign(sample=lambda m: m["year"].map(lambda y: "calibration" if y == CALIBRATION_YEAR else "out of sample"))
    gen_check = dp.generation_check(res)
    met.to_csv(out / "metrics.csv", index=False, float_format="%.3f")
    gen_check.to_csv(out / "generation_by_fuel.csv", index=False, float_format="%.3f")
    res[["ts_utc", "price", "model_price", "thermal_demand", "net_imports"]
        + [f"model_{f}" for f in dp.THERMAL]].to_csv(out / "hourly_model.csv", index=False, float_format="%.2f")

    summary = {
        "calibration": {"year": CALIBRATION_YEAR, "lignite_fuel_eur_mwh_th": float(best["lignite_fuel"]),
                        "must_run_quantile": float(best["must_run_q"]), "mae": float(best["mae"])},
        "assumptions": {f: vars(t) for f, t in dp.TECH.items()} | {"blocks_per_fuel": dp.N_BLOCKS},
        "metrics": met.round(3).to_dict(orient="records"),
        "generation_by_fuel": gen_check.round(2).to_dict(orient="records"),
        "net_imports_and_statistical_difference_twh": (df.groupby("year")["net_imports"].sum() / 1e6).round(1).to_dict(),
    }
    (out / "summary.json").write_text(json.dumps(summary, indent=2, default=str), encoding="utf-8")

    plots.dispatch_daily(res, figures / "dispatch_daily_prices.png")
    plots.dispatch_duration(res, figures / "dispatch_price_duration.png")
    plots.dispatch_generation(gen_check, figures / "dispatch_generation.png")
    return summary


if __name__ == "__main__":
    main()
