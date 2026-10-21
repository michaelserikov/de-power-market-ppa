"""Figures for the README (static PNG, light surface)."""

from __future__ import annotations

from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402

SURFACE, INK, INK2, GRID = "#fcfcfb", "#0b0b0b", "#52514e", "#e4e3df"
COLOR = {"wind_onshore": "#2a78d6", "solar": "#eb6834", "wind_offshore": "#1baf7a"}
LABEL = {"wind_onshore": "Wind onshore", "wind_offshore": "Wind offshore", "solar": "Solar"}
ORDER = ("wind_onshore", "solar", "wind_offshore")


def _style(ax, title: str, ylabel: str) -> None:
    ax.set_facecolor(SURFACE)
    ax.figure.set_facecolor(SURFACE)
    ax.set_title(title, loc="left", color=INK, fontsize=12, pad=12)
    ax.set_ylabel(ylabel, color=INK2)
    ax.tick_params(colors=INK2, length=0)
    ax.grid(axis="y", color=GRID, linewidth=0.8)
    ax.set_axisbelow(True)
    for side in ("top", "right", "left"):
        ax.spines[side].set_visible(False)
    ax.spines["bottom"].set_color(GRID)


def capture_rates(yearly: pd.DataFrame, out: Path) -> None:
    """Grouped bars: capture rate by technology and year."""
    years = sorted(yearly["year"].unique())
    fig, ax = plt.subplots(figsize=(8, 4.2))
    width = 0.26
    x = np.arange(len(years))
    for i, tech in enumerate(ORDER):
        vals = [yearly[(yearly.year == y) & (yearly.tech == tech)]["capture_rate"].iloc[0] for y in years]
        bars = ax.bar(x + (i - 1) * width, vals, width - 0.03, color=COLOR[tech], label=LABEL[tech])
        for b, v in zip(bars, vals):
            ax.text(b.get_x() + b.get_width() / 2, v + 0.01, f"{v:.0%}", ha="center", va="bottom", fontsize=8, color=INK2,
                    bbox=dict(facecolor=SURFACE, edgecolor="none", pad=1), zorder=4)
    ax.axhline(1, color=INK2, linewidth=1, linestyle=(0, (3, 3)))
    ax.text(-0.5, 1.015, "baseload price = 100%", ha="left", va="bottom", fontsize=8, color=INK2)
    ax.set_xticks(x, [str(y) for y in years])
    ax.set_ylim(0, 1.16)
    ax.yaxis.set_major_formatter(matplotlib.ticker.PercentFormatter(1.0))
    _style(ax, "Capture rate (capture price / baseload price), DE-LU day-ahead", "capture rate")
    ax.legend(frameon=False, ncols=3, loc="upper left", bbox_to_anchor=(0, -0.08), labelcolor=INK)
    fig.tight_layout()
    fig.savefig(out, dpi=160)
    plt.close(fig)


def monthly_prices(monthly: dict[str, pd.DataFrame], out: Path) -> None:
    """Lines: monthly baseload price and capture prices."""
    fig, ax = plt.subplots(figsize=(8, 4.2))
    base = monthly["solar"]
    t = pd.to_datetime(dict(year=base.year, month=base.month, day=1))
    ax.plot(t, base["baseload_price"], color=INK2, linewidth=2, label="Baseload")
    for tech in ORDER:
        m = monthly[tech]
        tt = pd.to_datetime(dict(year=m.year, month=m.month, day=1))
        ax.plot(tt, m["capture_price"], color=COLOR[tech], linewidth=2, label=LABEL[tech])
    _style(ax, "Monthly baseload and capture prices, DE-LU day-ahead", "EUR/MWh")
    ax.legend(frameon=False, ncols=4, loc="upper left", bbox_to_anchor=(0, -0.08), labelcolor=INK)
    fig.tight_layout()
    fig.savefig(out, dpi=160)
    plt.close(fig)


def cannibalisation(monthly_solar: pd.DataFrame, slope: float, intercept: float, out: Path) -> None:
    """Scatter: monthly solar capture rate against solar share of load, with the OLS line."""
    fig, ax = plt.subplots(figsize=(8, 4.2))
    shades = {2023: "#f4b08f", 2024: "#eb6834", 2025: "#a8401a"}
    for year, m in monthly_solar.groupby("year"):
        ax.scatter(m["share_of_load"], m["capture_rate"], s=42, color=shades.get(year, COLOR["solar"]),
                   edgecolor=SURFACE, linewidth=1.5, label=str(year), zorder=3)
    xs = np.linspace(monthly_solar["share_of_load"].min(), monthly_solar["share_of_load"].max(), 50)
    ax.plot(xs, intercept + slope * xs, color=INK2, linewidth=1.5, linestyle=(0, (4, 3)))
    ax.text(0.98, 0.95, f"OLS slope: {slope:+.1f} pp capture rate per +1 pp solar share",
            transform=ax.transAxes, ha="right", va="top", fontsize=9, color=INK2)
    ax.xaxis.set_major_formatter(matplotlib.ticker.PercentFormatter(1.0))
    ax.yaxis.set_major_formatter(matplotlib.ticker.PercentFormatter(1.0))
    _style(ax, "Solar cannibalisation: monthly capture rate vs solar share of load", "solar capture rate")
    ax.set_xlabel("solar generation / load (month)", color=INK2)
    ax.legend(frameon=False, title=None, loc="lower left", labelcolor=INK)
    fig.tight_layout()
    fig.savefig(out, dpi=160)
    plt.close(fig)


def pap_risk(results: dict[str, pd.DataFrame], out: Path) -> None:
    """Strip + box: offtaker result per MWh by month for a PaP PPA at the sample's fair strike."""
    fig, ax = plt.subplots(figsize=(8, 4.2))
    rng = np.random.default_rng(0)
    for i, tech in enumerate(ORDER):
        v = results[tech]["offtaker_eur_per_mwh"].to_numpy()
        ax.boxplot(v, positions=[i], widths=0.45, showfliers=False, patch_artist=True,
                   boxprops=dict(facecolor="none", edgecolor=INK2), medianprops=dict(color=INK),
                   whiskerprops=dict(color=INK2), capprops=dict(color=INK2))
        ax.scatter(i + rng.uniform(-0.15, 0.15, len(v)), v, s=22, color=COLOR[tech],
                   edgecolor=SURFACE, linewidth=1, zorder=3)
    ax.axhline(0, color=INK2, linewidth=1)
    ax.set_xticks(range(len(ORDER)), [LABEL[t] for t in ORDER])
    _style(ax, "Pay-as-produced PPA at the 2023-2025 fair strike: offtaker result by month", "EUR per MWh produced")
    ax.text(0, 1.0, "each dot = one month (spot value of the month's output minus strike); "
            "the generation-weighted mean is zero by construction",
            transform=ax.transAxes, fontsize=8, color=INK2, va="bottom")
    fig.tight_layout()
    fig.savefig(out, dpi=160)
    plt.close(fig)


# --- v0.2: model validation and market risk --------------------------------------------------

MODEL_COLOR = {"hs": "#2a78d6", "ewma": "#eb6834", "garch": "#1baf7a", "hs_cal": "#7c4dbd"}
MODEL_LABEL = {"hs": "Historical simulation", "ewma": "Normal, EWMA vol", "garch": "GARCH(1,1)-t",
               "hs_cal": "HS by day type"}


def mc_convergence(conv: pd.DataFrame, out: Path) -> None:
    """Monte Carlo estimate with a 95% band against the Black-76 price, by number of paths."""
    fig, ax = plt.subplots(figsize=(8, 4.2))
    ax.axhline(conv["black76"].iloc[0], color=INK2, linewidth=1.2, linestyle=(0, (4, 3)))
    ax.text(conv["n"].iloc[0], conv["black76"].iloc[0], " Black-76", va="bottom", fontsize=8, color=INK2)
    ax.errorbar(conv["n"], conv["mc"], yerr=1.96 * conv["mc_se"], fmt="o", color=COLOR["wind_onshore"],
                ecolor=COLOR["wind_onshore"], capsize=3, markersize=5, zorder=3)
    ax.set_xscale("log")
    _style(ax, "Monte Carlo vs Black-76, put K = 80, T = 0.5 (95% band)", "EUR/MWh")
    ax.set_xlabel("number of paths (antithetic)", color=INK2)
    fig.tight_layout()
    fig.savefig(out, dpi=160)
    plt.close(fig)


def floor_strip(strip: pd.DataFrame, strike: float, out: Path, strip_adj: pd.DataFrame | None = None) -> None:
    """Price of each monthly put of the floor under Black-76, its averaging fix and the challenger."""
    fig, ax = plt.subplots(figsize=(8, 4.2))
    x = np.arange(len(strip))
    ax.plot(x, strip["black76"], color=COLOR["solar"], linewidth=2, marker="o", markersize=4,
            label="Black-76, expiry at month end (model under validation)")
    ax.plot(x, strip["black76_avg_time"], color=INK2, linewidth=1.5, linestyle=(0, (4, 3)),
            label="Black-76, variance time of a monthly average")
    ax.plot(x, strip["challenger"], color=COLOR["wind_onshore"], linewidth=2, label="Challenger, two-factor (analytic)")
    ax.errorbar(x, strip["challenger_mc"], yerr=1.96 * strip["challenger_mc_se"], fmt="none",
                ecolor=COLOR["wind_onshore"], capsize=2, alpha=0.7, label="Challenger, Monte Carlo 95% band")
    if strip_adj is not None:
        ax.plot(x, strip_adj["challenger"], color=COLOR["wind_onshore"], linewidth=1.5, linestyle=(0, (1, 2)),
                label="Challenger, phi bias-corrected (+0.07)")
    ax.set_xticks(x, strip["month"], rotation=45, ha="right")
    _style(ax, f"Floor at {strike:.0f} EUR/MWh on the monthly average price: value of each monthly put",
           "EUR/MWh")
    ax.legend(frameon=False, loc="upper left", labelcolor=INK, fontsize=8)
    fig.tight_layout()
    fig.savefig(out, dpi=160)
    plt.close(fig)


def var_backtest(forecasts: dict[str, pd.DataFrame], out: Path) -> None:
    """Daily loss of the PPA offtaker against one-day 99% VaR forecasts; exceptions marked."""
    fig, axes = plt.subplots(len(forecasts), 1, figsize=(8, 3.4 * len(forecasts)), sharex=True)
    for ax, (tech, fc) in zip(np.atleast_1d(axes), forecasts.items()):
        ax.plot(fc.index, fc["loss"] / 1e3, color=INK2, alpha=0.35, linewidth=0.7, label="daily loss")
        for m in ("hs", "garch"):
            ax.plot(fc.index, fc[f"{m}_var"] / 1e3, color=MODEL_COLOR[m], linewidth=1.3, label=f"99% VaR, {MODEL_LABEL[m]}")
            hit = fc["loss"] > fc[f"{m}_var"]
            ax.scatter(fc.index[hit], fc["loss"][hit] / 1e3, s=14, color=MODEL_COLOR[m], zorder=3)
        lo, hi = np.percentile(fc["loss"] / 1e3, [0.5, 99.9])
        ax.set_ylim(lo * 1.1, max(hi, (fc[["hs_var", "garch_var"]].max().max() / 1e3)) * 1.1)
        _style(ax, f"{LABEL[tech]}: PaP PPA offtaker, 100 GWh/yr, daily loss vs 99% VaR", "thousand EUR")
    np.atleast_1d(axes)[0].legend(frameon=False, ncols=2, loc="upper left", fontsize=8, labelcolor=INK)
    fig.tight_layout()
    fig.savefig(out, dpi=160)
    plt.close(fig)


# --- v0.3: battery arbitrage ------------------------------------------------------------------

DUR_COLOR = {1.0: "#9ec5f0", 2.0: "#2a78d6", 4.0: "#123f7a"}


def storage_revenue(summary: pd.DataFrame, out: Path) -> None:
    """Grouped bars: day-ahead arbitrage profit per MW and year, by storage duration; naive share labelled."""
    years = sorted(summary["year"].unique())
    fig, ax = plt.subplots(figsize=(8, 4.2))
    width = 0.26
    x = np.arange(len(years))
    for i, (dur, g) in enumerate(summary.groupby("duration_h")):
        g = g.set_index("year").loc[years]
        bars = ax.bar(x + (i - 1) * width, g["profit_eur_per_mw"] / 1e3, width - 0.03,
                      color=DUR_COLOR.get(dur, INK2), label=f"{dur:.0f} h")
        for b_, v in zip(bars, g["profit_eur_per_mw"] / 1e3):
            ax.text(b_.get_x() + b_.get_width() / 2, v + 1, f"{v:.0f}", ha="center", va="bottom", fontsize=8, color=INK2)
    ax.set_xticks(x, [str(y) for y in years])
    _style(ax, "Battery day-ahead arbitrage, 1 MW, perfect day-ahead prices: profit by year", "thousand EUR per MW")
    ax.legend(frameon=False, ncols=3, loc="upper left", title="storage duration", title_fontsize=8, labelcolor=INK)
    fig.tight_layout()
    fig.savefig(out, dpi=160)
    plt.close(fig)


def storage_profile(profile: pd.DataFrame, out: Path) -> None:
    """Mean net discharge by hour of day (2-hour battery), one line per year."""
    shades = {2023: "#9ec5f0", 2024: "#2a78d6", 2025: "#123f7a"}
    fig, ax = plt.subplots(figsize=(8, 4.2))
    for year in profile.columns:
        ax.plot(profile.index, profile[year], color=shades.get(year, INK2), linewidth=2, label=str(year))
    ax.axhline(0, color=INK2, linewidth=1)
    ax.set_xticks(range(0, 24, 3))
    _style(ax, "When the 2-hour battery charges (<0) and discharges (>0): mean by local hour", "MW")
    ax.set_xlabel("hour of day (local time)", color=INK2)
    ax.legend(frameon=False, ncols=3, loc="upper left", bbox_to_anchor=(0, -0.14), labelcolor=INK)
    fig.tight_layout()
    fig.savefig(out, dpi=160)
    plt.close(fig)


def spreads_solar(monthly: pd.DataFrame, slope: float, intercept: float, out: Path) -> None:
    """Scatter: monthly mean daily spread (2 highest minus 2 lowest hours) against solar share of load."""
    fig, ax = plt.subplots(figsize=(8, 4.2))
    shades = {2023: "#f4b08f", 2024: "#eb6834", 2025: "#a8401a"}
    for year, m in monthly.groupby(level=0):
        ax.scatter(m["solar_share"], m["spread_2h"], s=42, color=shades.get(year, COLOR["solar"]),
                   edgecolor=SURFACE, linewidth=1.5, label=str(year), zorder=3)
    xs = np.linspace(monthly["solar_share"].min(), monthly["solar_share"].max(), 50)
    ax.plot(xs, intercept + slope * xs, color=INK2, linewidth=1.5, linestyle=(0, (4, 3)))
    ax.text(0.02, 0.95, f"OLS: {slope / 100:+.1f} EUR/MWh spread per +1 pp solar share",
            transform=ax.transAxes, ha="left", va="top", fontsize=9, color=INK2)
    ax.xaxis.set_major_formatter(matplotlib.ticker.PercentFormatter(1.0))
    _style(ax, "Daily price spread vs solar share of load, by month", "EUR/MWh (2 highest - 2 lowest hours)")
    ax.set_xlabel("solar generation / load (month)", color=INK2)
    ax.legend(frameon=False, loc="lower right", labelcolor=INK)
    fig.tight_layout()
    fig.savefig(out, dpi=160)
    plt.close(fig)


# --- v0.4: merit-order dispatch -----------------------------------------------------------------

FUEL_COLOR = {"lignite": "#8a5a2b", "hard_coal": "#52514e", "gas": "#2a78d6"}
FUEL_LABEL = {"lignite": "Lignite", "hard_coal": "Hard coal", "gas": "Gas"}


def dispatch_daily(res: pd.DataFrame, out: Path) -> None:
    """Daily mean day-ahead price: actual vs merit-order model."""
    day = res["ts_utc"].dt.tz_convert("Europe/Berlin").dt.tz_localize(None).dt.normalize()
    d = res.groupby(day)[["price", "model_price"]].mean()
    fig, ax = plt.subplots(figsize=(8, 4.2))
    ax.plot(d.index, d["price"], color=INK2, linewidth=1.1, label="Actual day-ahead")
    ax.plot(d.index, d["model_price"], color=COLOR["wind_onshore"], linewidth=1.1, label="Merit-order model")
    ax.axvline(pd.Timestamp("2024-01-01"), color=GRID, linewidth=1)
    ax.text(pd.Timestamp("2024-01-10"), ax.get_ylim()[1] * 0.95, "out of sample →", fontsize=8, color=INK2, va="top")
    _style(ax, "Daily mean price, DE-LU: actual vs merit-order model (calibrated on 2023)", "EUR/MWh")
    ax.legend(frameon=False, ncols=2, loc="upper left", bbox_to_anchor=(0, -0.08), labelcolor=INK)
    fig.tight_layout()
    fig.savefig(out, dpi=160)
    plt.close(fig)


def dispatch_duration(res: pd.DataFrame, out: Path) -> None:
    """Price duration curves (hours sorted by price) per year, actual dashed and model solid."""
    shades = {2023: "#9ec5f0", 2024: "#2a78d6", 2025: "#123f7a"}
    fig, ax = plt.subplots(figsize=(8, 4.2))
    for y, g in res.groupby("year"):
        share = np.linspace(0, 1, len(g))
        ax.plot(share, np.sort(g["price"].to_numpy())[::-1], color=shades.get(y, INK2), linestyle=(0, (4, 3)), linewidth=1.3)
        ax.plot(share, np.sort(g["model_price"].to_numpy())[::-1], color=shades.get(y, INK2), linewidth=1.8, label=str(y))
    ax.axhline(0, color=INK2, linewidth=0.8)
    ax.set_ylim(-150, 400)
    ax.xaxis.set_major_formatter(matplotlib.ticker.PercentFormatter(1.0))
    _style(ax, "Price duration curves: model (solid) vs actual (dashed)", "EUR/MWh")
    ax.set_xlabel("share of hours in the year", color=INK2)
    ax.legend(frameon=False, ncols=3, loc="upper right", labelcolor=INK)
    fig.tight_layout()
    fig.savefig(out, dpi=160)
    plt.close(fig)


def dispatch_generation(gen: pd.DataFrame, out: Path) -> None:
    """Annual thermal generation by fuel: actual (hatched) vs model."""
    years = sorted(gen["year"].unique())
    fig, ax = plt.subplots(figsize=(8, 4.2))
    width = 0.13
    x = np.arange(len(years))
    for i, f in enumerate(("lignite", "hard_coal", "gas")):
        g = gen[gen["fuel"] == f].set_index("year").loc[years]
        ax.bar(x + (2 * i - 2.5) * width, g["actual_twh"], width * 0.95, color="none", edgecolor=FUEL_COLOR[f],
               hatch="///", linewidth=1, label=f"{FUEL_LABEL[f]}, actual")
        ax.bar(x + (2 * i - 1.5) * width, g["model_twh"], width * 0.95, color=FUEL_COLOR[f], label=f"{FUEL_LABEL[f]}, model")
    ax.set_xticks(x, [str(y) for y in years])
    _style(ax, "Thermal generation by fuel: actual vs merit-order model", "TWh")
    ax.legend(frameon=False, ncols=3, loc="upper left", bbox_to_anchor=(0, -0.08), fontsize=8, labelcolor=INK)
    fig.tight_layout()
    fig.savefig(out, dpi=160)
    plt.close(fig)


# --- v0.5: price forecasting ----------------------------------------------------------------------

MODEL_STYLE = {"naive": ("#b8b6b0", "Naive"), "lear_avg": ("#2a78d6", "LEAR (avg of 364 and 728 days)"),
               "gbm": ("#1baf7a", "Gradient boosting"), "lear_gbm_avg": ("#123f7a", "LEAR + GBM average")}


def forecast_mae_by_hour(mae: pd.DataFrame, out: Path) -> None:
    fig, ax = plt.subplots(figsize=(8, 4.2))
    for m, (c, label) in MODEL_STYLE.items():
        ax.plot(mae.index, mae[m], color=c, linewidth=2, label=label, marker="o", markersize=3)
    ax.set_xticks(range(0, 24, 3))
    _style(ax, "Mean absolute error by hour of day, 2024-2025 out of sample", "EUR/MWh")
    ax.set_xlabel("hour of day (local time)", color=INK2)
    ax.legend(frameon=False, ncols=2, loc="upper left", fontsize=8, labelcolor=INK)
    fig.tight_layout()
    fig.savefig(out, dpi=160)
    plt.close(fig)


def forecast_example_week(actual: pd.DataFrame, fcs: dict, start: pd.Timestamp, out: Path) -> None:
    days = pd.date_range(start, periods=7, freq="D")
    t = pd.date_range(start, periods=7 * 24, freq="h")
    fig, ax = plt.subplots(figsize=(8, 4.2))
    ax.plot(t, actual.loc[days].to_numpy().ravel(), color=INK, linewidth=2, label="Actual")
    for m in ("naive", "lear_avg", "gbm"):
        c, label = MODEL_STYLE[m]
        ax.plot(t, fcs[m].loc[days].to_numpy().ravel(), color=c, linewidth=1.4, label=label)
    ax.axhline(0, color=INK2, linewidth=0.8)
    _style(ax, f"Day-ahead price and forecasts, week of {start.date()}", "EUR/MWh")
    ax.legend(frameon=False, ncols=4, loc="upper left", bbox_to_anchor=(0, -0.08), fontsize=8, labelcolor=INK)
    fig.tight_layout()
    fig.savefig(out, dpi=160)
    plt.close(fig)


def forecast_monthly_mae(actual: pd.DataFrame, fcs: dict, out: Path) -> None:
    fig, ax = plt.subplots(figsize=(8, 4.2))
    for m, (c, label) in MODEL_STYLE.items():
        e = (fcs[m] - actual).abs().mean(axis=1)
        mm = e.groupby(e.index.to_period("M")).mean()
        ax.plot(mm.index.to_timestamp(), mm.to_numpy(), color=c, linewidth=2, label=label)
    _style(ax, "Monthly mean absolute error, out of sample", "EUR/MWh")
    ax.legend(frameon=False, ncols=2, loc="upper left", fontsize=8, labelcolor=INK)
    fig.tight_layout()
    fig.savefig(out, dpi=160)
    plt.close(fig)


# --- v0.6: probabilistic forecasts and their value --------------------------------------------------

def fan_chart(actual: pd.DataFrame, qf: dict, start: pd.Timestamp, out: Path) -> None:
    days = pd.date_range(start, periods=7, freq="D")
    t = pd.date_range(start, periods=7 * 24, freq="h")
    fig, ax = plt.subplots(figsize=(8, 4.2))
    for lo, hi, alpha in ((0.05, 0.95, 0.18), (0.25, 0.75, 0.35)):
        ax.fill_between(t, qf[lo].loc[days].to_numpy().ravel(), qf[hi].loc[days].to_numpy().ravel(),
                        color="#2a78d6", alpha=alpha, linewidth=0, label=f"{int(lo * 100)}-{int(hi * 100)}% QRA interval")
    ax.plot(t, qf[0.5].loc[days].to_numpy().ravel(), color="#123f7a", linewidth=1.4, label="QRA median")
    ax.plot(t, actual.loc[days].to_numpy().ravel(), color=INK, linewidth=1.6, label="Actual")
    ax.axhline(0, color=INK2, linewidth=0.8)
    _style(ax, f"Probabilistic day-ahead forecast (QRA), week of {start.date()}", "EUR/MWh")
    ax.legend(frameon=False, ncols=4, loc="upper left", bbox_to_anchor=(0, -0.08), fontsize=8, labelcolor=INK)
    fig.tight_layout()
    fig.savefig(out, dpi=160)
    plt.close(fig)


def reliability(rel: pd.DataFrame, out: Path) -> None:
    fig, ax = plt.subplots(figsize=(5.6, 5))
    ax.plot([0, 1], [0, 1], color=INK2, linewidth=1, linestyle=(0, (4, 3)))
    for col, c, label in (("qra", "#2a78d6", "QRA"), ("historical_errors", "#eb6834", "Historical errors")):
        ax.plot(rel.index, rel[col], color=c, linewidth=2, marker="o", markersize=4, label=label)
    ax.set_xlim(0, 1); ax.set_ylim(0, 1)
    _style(ax, "Reliability: share of prices below each quantile", "observed frequency")
    ax.set_xlabel("nominal quantile level", color=INK2)
    ax.legend(frameon=False, loc="upper left", labelcolor=INK)
    fig.tight_layout()
    fig.savefig(out, dpi=160)
    plt.close(fig)


def battery_capture(capture: pd.DataFrame, out: Path) -> None:
    cols = [("lear_gbm_avg", "#123f7a", "LEAR + GBM"), ("lear_avg", "#2a78d6", "LEAR"), ("gbm", "#1baf7a", "GBM"),
            ("naive", "#b8b6b0", "Naive"), ("yesterday", "#eb6834", "Yesterday's prices")]
    years = capture.index.tolist()
    fig, ax = plt.subplots(figsize=(8, 4.2))
    width = 0.15
    x = np.arange(len(years))
    for i, (c, colour, label) in enumerate(cols):
        bars = ax.bar(x + (i - 2) * width, capture[c], width * 0.92, color=colour, label=label)
        for b_, v in zip(bars, capture[c]):
            ax.text(b_.get_x() + b_.get_width() / 2, v + 0.01, f"{v:.0%}", ha="center", va="bottom", fontsize=7, color=INK2)
    ax.set_xticks(x, [str(y) for y in years])
    ax.set_ylim(0, 1.1)
    ax.yaxis.set_major_formatter(matplotlib.ticker.PercentFormatter(1.0))
    _style(ax, "Battery scheduled on a forecast: share of the perfect-foresight profit", "share of profit")
    ax.legend(frameon=False, ncols=5, loc="upper left", bbox_to_anchor=(0, -0.08), fontsize=8, labelcolor=INK)
    fig.tight_layout()
    fig.savefig(out, dpi=160)
    plt.close(fig)


# --- v0.7: econometrics ---------------------------------------------------------------------------

def passthrough(m: pd.DataFrame, lr: dict, out: Path) -> None:
    """Monthly power price against the long-run fit from gas and CO2."""
    fit = lr["const"] + lr["b_gas"] * m["gas"] + lr["c_co2"] * m["co2"]
    t = m.index.to_timestamp()
    fig, ax = plt.subplots(figsize=(8, 4.2))
    ax.plot(t, m["power"], color=INK, linewidth=2, label="Baseload day-ahead, monthly mean")
    ax.plot(t, fit, color="#2a78d6", linewidth=2, linestyle=(0, (4, 2)),
            label=f"{lr['const']:.0f} + {lr['b_gas']:.2f} x gas + {lr['c_co2']:.2f} x CO2")
    ax.plot(t, m["gas"], color="#eb6834", linewidth=1.2, label="TTF gas, EUR/MWh thermal")
    _style(ax, "Fuel pass-through: monthly power price, 2020-2025", "EUR/MWh")
    ax.legend(frameon=False, loc="upper right", fontsize=8, labelcolor=INK)
    fig.tight_layout()
    fig.savefig(out, dpi=160)
    plt.close(fig)


def res_errors(errs: pd.DataFrame, by_hour: pd.DataFrame, out: Path) -> None:
    """Normalised MAE of TSO wind and solar forecasts by year, and MAE by hour of day."""
    fig, axes = plt.subplots(1, 2, figsize=(8, 3.8))
    for tech, c in (("wind", "#2a78d6"), ("solar", "#eb6834")):
        g = errs[errs["tech"] == tech]
        axes[0].plot(g["year"], g["nmae"], color=c, marker="o", linewidth=2, label=tech.capitalize())
        axes[1].plot(by_hour.index, by_hour[f"{tech}_mae"] / 1000, color=c, linewidth=2, label=tech.capitalize())
    axes[0].yaxis.set_major_formatter(matplotlib.ticker.PercentFormatter(1.0))
    _style(axes[0], "MAE / mean output", "")
    _style(axes[1], "MAE by hour, 2019-2025", "GW")
    axes[1].set_xticks(range(0, 24, 6))
    axes[0].legend(frameon=False, labelcolor=INK)
    fig.suptitle("TSO day-ahead forecasts of wind and solar generation: errors", x=0.02, ha="left", color=INK, fontsize=12)
    fig.tight_layout()
    fig.savefig(out, dpi=160)
    plt.close(fig)


# --- v0.8: battery under uncertainty --------------------------------------------------------------

LAM_COLOR = {0.0: "#9ec5f0", 0.25: "#5c9de3", 0.5: "#2a78d6", 0.75: "#1d5aa8", 1.0: "#123f7a"}


def risk_frontier(summ: pd.DataFrame, out: Path) -> None:
    """Expected profit against CVaR (mean of the worst 10% scenarios), per risk weight."""
    fig, ax = plt.subplots(figsize=(8, 4.2))
    ax.plot(summ["cvar_per_day"], summ["expected_per_day"], color=INK2, linewidth=1.2, zorder=1)
    for _, r in summ.iterrows():
        ax.scatter(r["cvar_per_day"], r["expected_per_day"], s=60, color=LAM_COLOR.get(r["lam"], INK2), zorder=3,
                   edgecolor=SURFACE)
        ax.annotate(f"lambda = {r['lam']:g}", (r["cvar_per_day"], r["expected_per_day"]), xytext=(6, 4),
                    textcoords="offset points", fontsize=8, color=INK2)
    _style(ax, "Risk-return frontier of the battery schedule (mean over days)", "expected profit, EUR per day")
    ax.set_xlabel("CVaR 10%: mean profit of the worst 10% of scenarios, EUR per day", color=INK2)
    fig.tight_layout()
    fig.savefig(out, dpi=160)
    plt.close(fig)


def evpi_vss(summ: pd.DataFrame, out: Path) -> None:
    fig, ax = plt.subplots(figsize=(8, 4.2))
    x = np.arange(len(summ))
    ax.bar(x - 0.18, summ["evpi_per_day"], 0.34, color="#2a78d6", label="EVPI: value of perfect information")
    ax.bar(x + 0.18, summ["vss_per_day"], 0.34, color="#eb6834", label="VSS: value of the stochastic solution")
    ax.set_xticks(x, [f"lambda = {l:g}" for l in summ["lam"]])
    _style(ax, "Value of information and of stochastic scheduling, by risk weight", "EUR per day (1 MW / 2 MWh)")
    ax.legend(frameon=False, loc="upper left", fontsize=8, labelcolor=INK)
    fig.tight_layout()
    fig.savefig(out, dpi=160)
    plt.close(fig)


def realised_tail(df: pd.DataFrame, lams, out: Path) -> None:
    """Lower tail of realised daily profits (actual prices) for each risk weight."""
    fig, ax = plt.subplots(figsize=(8, 4.2))
    for lam in lams:
        v = np.sort(df[f"realised_{lam}"].to_numpy())
        k = max(1, int(0.2 * len(v)))
        ax.plot(np.arange(1, k + 1) / len(v), v[:k], color=LAM_COLOR.get(lam, INK2), linewidth=2, label=f"lambda = {lam:g}")
    ax.axhline(0, color=INK2, linewidth=0.8)
    ax.xaxis.set_major_formatter(matplotlib.ticker.PercentFormatter(1.0))
    _style(ax, "Worst 20% of days at actual prices, by risk weight", "realised profit, EUR per day")
    ax.set_xlabel("share of days (sorted from worst)", color=INK2)
    ax.legend(frameon=False, loc="lower right", fontsize=8, labelcolor=INK)
    fig.tight_layout()
    fig.savefig(out, dpi=160)
    plt.close(fig)
