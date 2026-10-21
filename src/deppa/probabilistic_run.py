"""Run v0.6: probabilistic price forecasts and the value of forecasts for a battery.

    python -m deppa.probabilistic_run   # needs the v0.5 forecasts (python -m deppa.forecast_run)

Quantile forecasts are evaluated from 2024-07-01 (the first 182 days of v0.5 forecasts calibrate
them); the battery uses all of 2024-2025. Writes results/probabilistic/ and figures/.
"""

from __future__ import annotations

import json

import numpy as np
import pandas as pd

from . import plots, probabilistic as pr
from .run import ROOT

PROB_START = "2024-07-01"


def _read(path) -> pd.DataFrame:
    df = pd.read_csv(path, index_col=0, parse_dates=True)
    df.columns = df.columns.astype(int)
    return df


def main() -> dict:
    src, out, figs = ROOT / "results" / "forecast", ROOT / "results" / "probabilistic", ROOT / "figures"
    out.mkdir(parents=True, exist_ok=True)
    actual = _read(src / "actual.csv")
    point = {n: _read(src / f"forecast_{n}.csv") for n in ("naive", "lear_avg", "gbm", "lear_gbm_avg")}
    days = actual.loc[PROB_START:].index

    qf = {"qra": pr.qra(actual, {"lear_avg": point["lear_avg"], "gbm": point["gbm"]}, days),
          "historical_errors": pr.historical_errors(actual, point["lear_gbm_avg"], days)}
    rows = []
    for name, q in qf.items():
        for period, sel in (("2024 H2", days.year == 2024), ("2025", days.year == 2025), ("all", slice(None))):
            a = actual.loc[days][sel]
            qs = {lv: f[sel] for lv, f in q.items()}
            c80, c90 = pr.coverage(a, qs, 0.8), pr.coverage(a, qs, 0.9)
            rows.append({"method": name, "period": period, "pinball": pr.pinball(a, qs),
                         "coverage_80": c80["coverage"], "kupiec_p_80": c80["kupiec_p"], "width_80": c80["mean_width"],
                         "coverage_90": c90["coverage"], "kupiec_p_90": c90["kupiec_p"], "width_90": c90["mean_width"]})
    scores = pd.DataFrame(rows)
    scores.to_csv(out / "scores.csv", index=False, float_format="%.4f")
    reliability = pd.DataFrame({name: [float((actual.loc[days].to_numpy() <= q[lv].to_numpy()).mean()) for lv in pr.LEVELS]
                                for name, q in qf.items()}, index=pr.LEVELS)
    reliability.index.name = "nominal_level"
    reliability.to_csv(out / "reliability.csv", float_format="%.4f")
    for lv in (0.05, 0.5, 0.95):
        qf["qra"][lv].to_csv(out / f"qra_q{int(lv * 100):02d}.csv", float_format="%.3f")

    yesterday = actual.shift(1)
    sched = {"lear_gbm_avg": point["lear_gbm_avg"], "lear_avg": point["lear_avg"], "gbm": point["gbm"],
             "naive": point["naive"], "yesterday": yesterday}
    val = pr.battery_value(actual.iloc[1:], {k: v.iloc[1:] for k, v in sched.items()})
    val.to_csv(out / "battery_daily.csv", float_format="%.2f")
    by_year = val.groupby(val.index.year).sum()
    capture = by_year.div(by_year["perfect"], axis=0)
    by_year.to_csv(out / "battery_profit_by_year.csv", float_format="%.1f")
    capture.to_csv(out / "battery_capture_by_year.csv", float_format="%.4f")

    summary = {"prob_period": [str(days[0].date()), str(days[-1].date())],
               "scores": scores.round(4).to_dict(orient="records"),
               "battery_profit_eur_per_mw": by_year.round(0).to_dict(orient="index"),
               "battery_capture": capture.round(4).to_dict(orient="index")}
    (out / "summary.json").write_text(json.dumps(summary, indent=2, default=str), encoding="utf-8")

    plots.fan_chart(actual, qf["qra"], pd.Timestamp("2025-05-05"), figs / "forecast_fan_chart.png")
    plots.reliability(reliability, figs / "forecast_reliability.png")
    plots.battery_capture(capture, figs / "forecast_battery_value.png")
    return summary


if __name__ == "__main__":
    main()
