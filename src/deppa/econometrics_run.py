"""Run v0.7: fuel pass-through econometrics (2020-2025, monthly) and renewable forecast errors (2019-2025, hourly).

    python -m deppa.econometrics_run

Writes results/econometrics/ and figures/.
"""

from __future__ import annotations

import json

import numpy as np
import pandas as pd

from . import econometrics as ec, fuels, plots, smard
from .run import ROOT, load_hourly

MONTHLY_START, HOURLY_START, END = "2020-01", "2019-01-01", "2025-12-31"


def main() -> dict:
    data, out, figs = ROOT / "data", ROOT / "results" / "econometrics", ROOT / "figures"
    out.mkdir(parents=True, exist_ok=True)

    hourly = load_hourly(HOURLY_START, END, data)
    fcs = smard.load_forecasts((pd.Timestamp(HOURLY_START) - pd.Timedelta(days=1)).date().isoformat(), END, data / "raw")
    df = hourly.merge(fcs, on="ts_utc", how="left")

    # 1. fuel pass-through, monthly
    fp = fuels.monthly_prices(data / "raw" / "fuels", MONTHLY_START, END[:7])
    power = df.groupby(["year", "month"])["price"].mean()
    power.index = pd.PeriodIndex([f"{y}-{m:02d}" for y, m in power.index], freq="M")
    m = pd.DataFrame({"power": power, "gas": fp["gas_eur_mwh"], "co2": fp["co2_eur_t"]}).dropna()
    m.to_csv(out / "monthly_prices.csv", float_format="%.3f")
    ur = ec.unit_roots({c: m[c] for c in m.columns})
    ur.to_csv(out / "unit_roots.csv", index=False, float_format="%.4f")
    lr = ec.long_run(m["power"], m["gas"], m["co2"])
    lr_post = ec.long_run(m.loc["2023-01":, "power"], m.loc["2023-01":, "gas"], m.loc["2023-01":, "co2"])
    var = ec.var_analysis(m)

    # 2. renewable forecast errors and the price slope
    errs = ec.forecast_errors(df)
    errs.to_csv(out / "res_forecast_errors.csv", index=False, float_format="%.4f")
    slope = ec.price_slope(df)
    wind_err = (df["onshore_fc"] + df["offshore_fc"]) - (df["wind_onshore"] + df["wind_offshore"])
    solar_err = df["solar_fc"] - df["solar"]
    by_hour = pd.DataFrame({"wind_mae": wind_err.abs().groupby(df["hour_local"]).mean(),
                            "solar_mae": solar_err.abs().groupby(df["hour_local"]).mean()})
    by_hour.to_csv(out / "res_forecast_mae_by_hour.csv", float_format="%.1f")
    price_equiv = {}
    for y, s in slope.items():
        sel = df["year"] == y
        e = (wind_err + solar_err)[sel].abs().mean() / 1000      # GW
        price_equiv[y] = {"res_error_mae_gw": float(e), "price_equivalent_eur_mwh": float(e * s["slope_eur_mwh_per_gw"])}

    summary = {"monthly_period": [str(m.index[0]), str(m.index[-1])], "months": int(len(m)),
               "unit_roots": ur.round(4).to_dict(orient="records"),
               "long_run_2020_2025": lr, "long_run_2023_2025": lr_post, "var": var,
               "res_forecast_errors": errs.round(4).to_dict(orient="records"),
               "price_slope_by_year": slope, "price_equivalent_of_res_errors": price_equiv}
    (out / "summary.json").write_text(json.dumps(summary, indent=2, default=str), encoding="utf-8")

    plots.passthrough(m, lr, figs / "econometrics_passthrough.png")
    plots.res_errors(errs, by_hour, figs / "res_forecast_errors.png")
    return summary


if __name__ == "__main__":
    main()
