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
