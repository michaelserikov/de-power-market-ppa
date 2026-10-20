"""Run the v0.2 market-risk and model-validation module: floor valuation checks and VaR/ES backtests.

    python -m deppa.validate             # uses the cached 2023-2025 data (downloads if missing)

Writes CSV/JSON to results/validation/ and figures to figures/.
"""

from __future__ import annotations

import argparse
import json

import numpy as np
import pandas as pd

from . import plots, ppa, risk, valuation as val
from .run import ROOT, load_hourly

PRICING_DATE = pd.Timestamp("2025-12-31")
RATE = 0.02            # illustrative discount rate
FLOOR_STRIKE = 60.0    # EUR/MWh, floor level of the illustrative PPA floor
RISK_TECHS = ("solar", "wind_onshore")
PHI_BIAS = 0.07        # downward bias of the challenger's AR(1) estimate measured on synthetic data


def daily_prices(hourly: pd.DataFrame) -> pd.Series:
    """Daily (local calendar) mean day-ahead price, naive local dates as index."""
    local = hourly["ts_utc"].dt.tz_convert("Europe/Berlin").dt.tz_localize(None).dt.normalize()
    return hourly["price"].groupby(local).mean().rename("price")


def replication(F: float, sigma: float) -> pd.DataFrame:
    """Black-76 against Monte Carlo on a grid of strikes and maturities; z = difference / standard error."""
    rows = []
    for T in (0.25, 0.5, 1.0):
        for K in (40, 60, 80, 100, 120):
            for kind in ("put", "call"):
                b = val.black76(F, K, T, sigma, RATE, kind)
                mc, se = val.mc_black76(F, K, T, sigma, RATE, kind, n=400_000, seed=K + int(100 * T))
                rows.append({"T": T, "K": K, "kind": kind, "black76": b, "mc": mc, "mc_se": se, "z": (mc - b) / se})
    df = pd.DataFrame(rows)
    # Put-call parity: C - P = df * (F - K)
    piv = df.pivot_table(index=["T", "K"], columns="kind", values="black76").reset_index()
    piv["parity_error"] = piv["call"] - piv["put"] - np.exp(-RATE * piv["T"]) * (F - piv["K"])
    return df.merge(piv[["T", "K", "parity_error"]], on=["T", "K"])


def convergence(F: float, sigma: float, K: float, T: float) -> pd.DataFrame:
    rows = []
    for n in (1_000, 4_000, 16_000, 64_000, 256_000, 1_024_000):
        mc, se = val.mc_black76(F, K, T, sigma, RATE, "put", n=n, seed=7)
        rows.append({"n": n, "mc": mc, "mc_se": se})
    out = pd.DataFrame(rows)
    out["black76"] = val.black76(F, K, T, sigma, RATE, "put")
    return out


def greeks_check(F: float, sigma: float) -> pd.DataFrame:
    """Analytic Greeks against finite differences of the formula and against bumped Monte Carlo (common random numbers)."""
    rows = []
    for K, T in ((60, 0.5), (80, 0.5), (100, 1.0)):
        a = val.black76_greeks(F, K, T, sigma, RATE)
        b = val.bump_greeks(F, K, T, sigma, RATE)
        hF, hs = 0.01 * F, 0.01
        mc = lambda f=F, s=sigma: val.mc_black76(f, K, T, s, RATE, n=400_000, seed=11)[0]  # noqa: E731
        mc_delta = (mc(f=F + hF) - mc(f=F - hF)) / (2 * hF)
        mc_vega = (mc(s=sigma + hs) - mc(s=sigma - hs)) / (2 * hs)
        for g in ("delta", "gamma", "vega", "dV_dT"):
            rows.append({"K": K, "T": T, "greek": g, "analytic": a[g], "finite_difference": b[g],
                         "mc_bump": {"delta": mc_delta, "vega": mc_vega}.get(g, np.nan)})
    return pd.DataFrame(rows)


def sensitivity(F: float, sigma: float, T: float = 0.5) -> pd.DataFrame:
    """Ladder of the floor put price under forward and volatility shifts."""
    rows = []
    for dF in (-0.2, -0.1, 0.0, 0.1, 0.2):
        for dS in (-0.2, -0.1, 0.0, 0.1, 0.2):
            rows.append({"forward_shift": dF, "vol_shift_abs": dS,
                         "put": val.black76(F * (1 + dF), FLOOR_STRIKE, T, sigma + dS, RATE)})
    return pd.DataFrame(rows).pivot(index="forward_shift", columns="vol_shift_abs", values="put")


def main(argv: list[str] | None = None) -> dict:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--start", default="2023-01-01")
    ap.add_argument("--end", default="2025-12-31")
    args = ap.parse_args(argv)
    out, figures = ROOT / "results" / "validation", ROOT / "figures"
    out.mkdir(parents=True, exist_ok=True)

    hourly = load_hourly(args.start, args.end)
    daily = daily_prices(hourly)

    # --- Valuation ---------------------------------------------------------------------------
    F = float(daily[str(PRICING_DATE.year)].mean())  # forward proxy: last year's baseload average
    sigma = val.monthly_log_vol(daily)
    tf = val.calibrate_two_factor(daily)
    rep = replication(F, sigma)
    conv = convergence(F, sigma, K=80, T=0.5)
    grk = greeks_check(F, sigma)
    sens = sensitivity(F, sigma)
    strip = val.floor_strip(F, FLOOR_STRIKE, sigma, tf, PRICING_DATE, r=RATE)
    rep.to_csv(out / "replication.csv", index=False, float_format="%.6f")
    conv.to_csv(out / "mc_convergence.csv", index=False, float_format="%.6f")
    grk.to_csv(out / "greeks.csv", index=False, float_format="%.6f")
    sens.to_csv(out / "sensitivity_put_6m.csv", float_format="%.4f")
    strip.to_csv(out / "floor_strip.csv", index=False, float_format="%.4f")

    # Challenger sensitivity to the known downward bias of its phi estimate (see calibrate_two_factor)
    tf_adj = val.calibrate_two_factor(daily, phi_override=tf.phi + PHI_BIAS)
    strip_adj = val.floor_strip(F, FLOOR_STRIKE, sigma, tf_adj, PRICING_DATE, r=RATE, mc_paths=2_000)
    strip_tot = strip[["black76", "black76_avg_time", "challenger", "challenger_mc"]].sum()
    summary: dict = {
        "pricing_date": PRICING_DATE.date().isoformat(), "rate": RATE, "forward_proxy": F,
        "floor_strike": FLOOR_STRIKE, "black76_sigma": sigma,
        "two_factor": {"phi": tf.phi, "half_life_days": tf.half_life_days, "sigma_short": tf.sigma_short,
                       "sigma_level_daily": tf.sigma_level, "sigma_level_annual": tf.sigma_level * np.sqrt(365),
                       "weekday_effects": dict(zip("Mon Tue Wed Thu Fri Sat Sun".split(), tf.weekday.round(2).tolist()))},
        "replication": {"max_abs_z": float(rep["z"].abs().max()), "share_abs_z_below_3": float((rep["z"].abs() < 3).mean()),
                        "max_abs_parity_error": float(rep["parity_error"].abs().max())},
        "greeks_max_rel_error_fd": float(((grk["analytic"] - grk["finite_difference"]).abs()
                                          / grk["analytic"].abs()).max()),
        "floor_strip_eur_per_mwh_month": {k: float(v) for k, v in strip_tot.items()},
        "floor_strip_black76_overvaluation": float(strip_tot["black76"] / strip_tot["challenger"] - 1),
        "floor_strip_avg_time_overvaluation": float(strip_tot["black76_avg_time"] / strip_tot["challenger"] - 1),
        "challenger_phi_bias_check": {"phi_adjusted": tf_adj.phi, "sigma_level_daily": tf_adj.sigma_level,
                                      "strip_challenger": float(strip_adj["challenger"].sum()),
                                      "change_vs_base": float(strip_adj["challenger"].sum() / strip_tot["challenger"] - 1)},
        "challenger_mc_max_abs_z": float(((strip["challenger_mc"] - strip["challenger"]) / strip["challenger_mc_se"]).abs().max()),
    }

    # --- Market risk -------------------------------------------------------------------------
    tables, forecasts = [], {}
    for tech in RISK_TECHS:
        strike = ppa.fair_pap_strike(hourly, tech)
        pnl = risk.daily_pnl(hourly, tech, strike)
        fc = risk.rolling_forecasts(pnl)
        fc.to_csv(out / f"var_forecasts_{tech}.csv", float_format="%.2f")
        forecasts[tech] = fc
        tables.append(risk.backtest(fc).assign(tech=tech, strike=strike))
        summary[f"pnl_{tech}"] = {"strike": strike, "days": int(len(pnl)), "std": float(pnl.std()),
                                  "worst_day": float(pnl.min()), "worst_date": pnl.idxmin().date().isoformat()}
    bt = pd.concat(tables, ignore_index=True)
    bt.to_csv(out / "backtest.csv", index=False, float_format="%.4f")
    summary["backtest"] = bt.round(4).to_dict(orient="records")
    (out / "summary.json").write_text(json.dumps(summary, indent=2, default=str), encoding="utf-8")

    plots.mc_convergence(conv, figures / "mc_convergence.png")
    plots.floor_strip(strip, FLOOR_STRIKE, figures / "floor_strip.png", strip_adj)
    plots.var_backtest(forecasts, figures / "var_backtest.png")
    return summary


if __name__ == "__main__":
    main()
