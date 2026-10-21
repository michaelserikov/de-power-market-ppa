"""Run the v0.5 price-forecasting study: 2024 and 2025 out of sample.

    python -m deppa.forecast_run      # about 20-30 minutes (weekly LEAR recalibration, monthly GBM)

Writes results/forecast/ (forecasts per model, metrics, Diebold-Mariano p-values) and figures/.
"""

from __future__ import annotations

import json

import numpy as np
import pandas as pd

from . import forecast as fc, fuels, plots, smard
from .run import ROOT, load_hourly

TEST_START, TEST_END = "2024-01-01", "2025-12-31"
DATA_START = "2021-01-01"


def load_inputs() -> dict:
    data = ROOT / "data"
    hourly = load_hourly(DATA_START, TEST_END, data)
    first_day = (pd.Timestamp(DATA_START) - pd.Timedelta(days=1)).date().isoformat()
    forecasts = smard.load_forecasts(first_day, TEST_END, data / "raw")
    cache = data / "raw" / "fuels"
    eua = fuels.eua_auctions(cache, range(int(DATA_START[:4]), int(TEST_END[:4]) + 1))
    gas = fuels.monthly_prices(cache, DATA_START[:7], TEST_END[:7])["gas_eur_mwh"]
    return fc.build_inputs(hourly, forecasts, eua, gas)


def main() -> dict:
    out, figs = ROOT / "results" / "forecast", ROOT / "figures"
    out.mkdir(parents=True, exist_ok=True)
    inp = load_inputs()
    days = pd.date_range(TEST_START, TEST_END, freq="D")
    actual = inp["price"].loc[days]

    fcs = {"naive": fc.naive(inp["price"], days),
           "lear_364": fc.lear(inp, days, 364),
           "lear_728": fc.lear(inp, days, 728),
           "gbm": fc.gbm(inp, days)}
    fcs["lear_avg"] = (fcs["lear_364"] + fcs["lear_728"]) / 2
    fcs["lear_gbm_avg"] = (fcs["lear_avg"] + fcs["gbm"]) / 2
    actual.to_csv(out / "actual.csv", float_format="%.3f")
    for name, f in fcs.items():
        f.to_csv(out / f"forecast_{name}.csv", float_format="%.3f")

    rows = []
    for year in (2024, 2025):
        sel = actual.index.year == year
        for name, f in fcs.items():
            rows.append({"year": year, "model": name, **fc.metrics(actual[sel], f[sel], fcs["naive"][sel])})
    for name, f in fcs.items():
        rows.append({"year": "2024-2025", "model": name, **fc.metrics(actual, f, fcs["naive"])})
    met = pd.DataFrame(rows)
    met.to_csv(out / "metrics.csv", index=False, float_format="%.4f")

    names = list(fcs)
    dm = pd.DataFrame(index=names, columns=names, dtype=float)
    for a in names:
        for b in names:
            if a != b:
                dm.loc[a, b] = fc.dm_test(actual, fcs[a], fcs[b])[1]   # p-value: column model better than row model
    dm.to_csv(out / "dm_pvalues.csv", float_format="%.4f")

    hourly_mae = pd.DataFrame({n: (f - actual).abs().mean() for n, f in fcs.items()})
    hourly_mae.to_csv(out / "mae_by_hour.csv", float_format="%.3f")
    summary = {"test_period": [TEST_START, TEST_END], "days": int(len(days)),
               "metrics": met.round(3).to_dict(orient="records"),
               "dm_pvalues_column_better_than_row": dm.round(4).to_dict()}
    (out / "summary.json").write_text(json.dumps(summary, indent=2, default=str), encoding="utf-8")

    plots.forecast_mae_by_hour(hourly_mae, figs / "forecast_mae_by_hour.png")
    plots.forecast_example_week(actual, fcs, pd.Timestamp("2025-05-05"), figs / "forecast_example_week.png")
    plots.forecast_monthly_mae(actual, fcs, figs / "forecast_monthly_mae.png")
    return summary


if __name__ == "__main__":
    main()
