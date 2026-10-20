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
