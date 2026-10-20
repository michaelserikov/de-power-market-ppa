"""Valuation of a price floor (a strip of monthly puts) and an independent challenger model.

Model under validation (the "front-office" model): Black-76 on the monthly average day-ahead
price, with one constant volatility calibrated to month-on-month log changes of monthly averages.

Checks against it:
- Monte Carlo replication of Black-76 (same lognormal assumption, independent implementation);
- analytic Greeks against bump-and-revalue;
- a challenger model: daily prices = random-walk level + weekday effect + mean-reverting
  short-term deviation (arithmetic, so negative prices are possible); the option pays on the
  arithmetic average over the delivery month. Calibrated on daily prices, not on the monthly
  log series, so it is an independent view of the same risk.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd
from scipy.optimize import brentq
from scipy.stats import norm


# --- Black-76 -----------------------------------------------------------------------------

def _d1d2(F: float, K: float, T: float, sigma: float) -> tuple[float, float]:
    sd = sigma * np.sqrt(T)
    d1 = (np.log(F / K) + 0.5 * sd**2) / sd
    return d1, d1 - sd


def black76(F: float, K: float, T: float, sigma: float, r: float = 0.0, kind: str = "put") -> float:
    """Black-76 price of a European call or put on a forward F, discounted at rate r."""
    df = np.exp(-r * T)
    d1, d2 = _d1d2(F, K, T, sigma)
    if kind == "call":
        return float(df * (F * norm.cdf(d1) - K * norm.cdf(d2)))
    if kind == "put":
        return float(df * (K * norm.cdf(-d2) - F * norm.cdf(-d1)))
    raise ValueError("kind must be 'call' or 'put'")


def black76_greeks(F: float, K: float, T: float, sigma: float, r: float = 0.0, kind: str = "put") -> dict:
    """Analytic delta (dV/dF), gamma, vega (per unit of sigma) and dV/dT (time to expiry)."""
    df = np.exp(-r * T)
    d1, _ = _d1d2(F, K, T, sigma)
    pdf = norm.pdf(d1)
    delta = df * norm.cdf(d1) if kind == "call" else -df * norm.cdf(-d1)
    v = black76(F, K, T, sigma, r, kind)
    return {
        "delta": float(delta),
        "gamma": float(df * pdf / (F * sigma * np.sqrt(T))),
        "vega": float(df * F * pdf * np.sqrt(T)),
        "dV_dT": float(-r * v + df * F * pdf * sigma / (2 * np.sqrt(T))),
    }


def bump_greeks(F: float, K: float, T: float, sigma: float, r: float = 0.0, kind: str = "put",
                rel: float = 1e-4) -> dict:
    """Central finite differences of the Black-76 price, as an independent check of the formulas."""
    def p(f=F, t=T, s=sigma):
        return black76(f, K, t, s, r, kind)
    hF, hT, hs = F * rel, T * rel, sigma * rel
    return {
        "delta": (p(f=F + hF) - p(f=F - hF)) / (2 * hF),
        "gamma": (p(f=F + hF) - 2 * p() + p(f=F - hF)) / hF**2,
        "vega": (p(s=sigma + hs) - p(s=sigma - hs)) / (2 * hs),
        "dV_dT": (p(t=T + hT) - p(t=T - hT)) / (2 * hT),
    }


def implied_vol(price: float, F: float, K: float, T: float, r: float = 0.0, kind: str = "put") -> float:
    """Black-76 volatility that reproduces `price` (NaN if the price is outside the no-arbitrage range)."""
    try:
        return float(brentq(lambda s: black76(F, K, T, s, r, kind) - price, 1e-4, 5.0, xtol=1e-10))
    except ValueError:
        return float("nan")


def mc_black76(F: float, K: float, T: float, sigma: float, r: float = 0.0, kind: str = "put",
               n: int = 100_000, seed: int = 0, antithetic: bool = True) -> tuple[float, float]:
    """Monte Carlo price and standard error under the Black-76 (driftless lognormal forward) assumption."""
    z = np.random.default_rng(seed).standard_normal(n // 2 if antithetic else n)
    if antithetic:
        z = np.concatenate([z, -z])
    FT = F * np.exp(-0.5 * sigma**2 * T + sigma * np.sqrt(T) * z)
    pay = np.maximum(FT - K, 0) if kind == "call" else np.maximum(K - FT, 0)
    pay = np.exp(-r * T) * pay
    if antithetic:  # pairs are dependent: estimate the error from pair means
        pair = 0.5 * (pay[: len(z) // 2] + pay[len(z) // 2:])
        return float(pair.mean()), float(pair.std(ddof=1) / np.sqrt(len(pair)))
    return float(pay.mean()), float(pay.std(ddof=1) / np.sqrt(n))


def monthly_log_vol(daily_price: pd.Series) -> float:
    """Front-office calibration: annualised std of month-on-month log changes of monthly average prices."""
    m = daily_price.groupby([daily_price.index.year, daily_price.index.month]).mean()
    return float(np.log(m).diff().dropna().std(ddof=1) * np.sqrt(12))


# --- Challenger: two-factor arithmetic model on daily prices ----------------------------------

@dataclass
class TwoFactorParams:
    """Daily price = level + weekday effect + short-term deviation (arithmetic, so prices can go negative).

    The level is a driftless random walk (the forward is a martingale); the deviation is an AR(1),
    i.e. a discretised Ornstein-Uhlenbeck process. A Schwartz-Smith type split, in EUR/MWh.
    """
    phi: float               # daily AR(1) coefficient of the short-term deviation
    sigma_short: float       # std of daily shocks to the deviation, EUR/MWh
    sigma_level: float       # std of daily shocks to the level, EUR/MWh
    weekday: np.ndarray      # additive weekday effects (Mon..Sun), mean zero, EUR/MWh

    @property
    def half_life_days(self) -> float:
        return float(np.log(2) / -np.log(self.phi))


def _block_cov(p: TwoFactorParams, t: np.ndarray, short: bool = True, level: bool = True) -> np.ndarray:
    """Covariance of the model's daily deviations from today's level at days t (deviation starts at zero)."""
    i, j = np.meshgrid(t, t)
    cov = np.zeros(i.shape)
    if short:
        cov += p.sigma_short**2 * p.phi ** np.abs(i - j) * (1 - p.phi ** (2 * np.minimum(i, j))) / (1 - p.phi**2)
    if level:
        cov += p.sigma_level**2 * np.minimum(i, j)
    return cov


def calibrate_two_factor(daily_price: pd.Series, phi_override: float | None = None) -> TwoFactorParams:
    """Calibrate on daily prices in two steps.

    1. Short-term part: deviations from a 28-day centred mean, minus weekday effects, fitted as AR(1) by OLS.
    `phi_override` fixes the AR(1) coefficient (sensitivity runs); the other parameters are then refitted.
    Note: removing the centred mean biases the OLS phi down (about -0.07 on synthetic AR(1) data
    with phi of 0.5-0.6, see tests); the validation run reports the price impact of that bias.

    2. Level: variance of month-on-month changes of monthly average prices, after removing what the
       short-term part already explains, divided by the variance a unit random walk gives to the same
       statistic (two consecutive 30-day averages).
    """
    level = daily_price.rolling(28, center=True, min_periods=14).mean()
    dev = (daily_price - level).dropna()
    wd = dev.groupby(dev.index.dayofweek).mean().reindex(range(7)).to_numpy()
    wd = wd - wd.mean()
    x = (dev - wd[dev.index.dayofweek]).to_numpy()
    x0, x1 = x[:-1] - x[:-1].mean(), x[1:] - x[1:].mean()
    phi = float(np.dot(x0, x1) / np.dot(x0, x0)) if phi_override is None else phi_override
    sigma_short = float((x1 - phi * x0).std(ddof=2))

    monthly = daily_price.groupby([daily_price.index.year, daily_price.index.month]).mean()
    var_dm = float(monthly.diff().dropna().var(ddof=1))
    t = np.arange(1, 61)
    w = np.r_[-np.ones(30), np.ones(30)] / 30  # second 30-day average minus first
    unit = TwoFactorParams(phi, 0.0, 1.0, wd)
    # Short-term part in steady state: start it far in the past so the initial zero has decayed.
    stat = TwoFactorParams(phi, sigma_short, 0.0, wd)
    var_short = float(w @ _block_cov(stat, t + 1000, level=True) @ w)
    var_unit = float(w @ _block_cov(unit, t, short=False) @ w)
    sigma_level = float(np.sqrt(max(var_dm - var_short, 0.0) / var_unit))
    return TwoFactorParams(phi=phi, sigma_short=sigma_short, sigma_level=sigma_level, weekday=wd)


def average_std(p: TwoFactorParams, start_day: int, n_days: int) -> float:
    """Std of the arithmetic average price over days start_day+1 .. start_day+n_days, seen from today."""
    t = np.arange(start_day + 1, start_day + n_days + 1)
    return float(np.sqrt(_block_cov(p, t).mean()))


def bachelier_put(F: float, K: float, sd: float, df: float = 1.0) -> float:
    """Put on a normally distributed underlying with mean F and std sd (here: the monthly average)."""
    d = (F - K) / sd
    return float(df * ((K - F) * norm.cdf(-d) + sd * norm.pdf(d)))


def mc_average_put(F: float, K: float, p: TwoFactorParams, start: pd.Timestamp, month_start: pd.Timestamp,
                   r: float = 0.0, n: int = 50_000, seed: int = 0) -> tuple[float, float]:
    """Monte Carlo put on the monthly average of simulated daily prices (level + weekday + deviation)."""
    month_end = month_start + pd.offsets.MonthEnd(0)
    days = pd.date_range(start + pd.Timedelta(days=1), month_end, freq="D")
    rng = np.random.default_rng(seed)
    in_month = days >= month_start
    # Weekday effects re-centred on the month, so the expected monthly average equals the forward F.
    wd = p.weekday[days.dayofweek] - p.weekday[days[in_month].dayofweek].mean()
    x, lvl, acc = np.zeros(n), np.full(n, F), np.zeros(n)
    for w, inside in zip(wd, in_month):
        x = p.phi * x + p.sigma_short * rng.standard_normal(n)
        lvl = lvl + p.sigma_level * rng.standard_normal(n)
        if inside:
            acc += lvl + w + x
    avg = acc / in_month.sum()
    T = (month_end - start).days / 365
    pay = np.exp(-r * T) * np.maximum(K - avg, 0)
    return float(pay.mean()), float(pay.std(ddof=1) / np.sqrt(n))


def floor_strip(F: float, K: float, sigma: float, p: TwoFactorParams, pricing_date: pd.Timestamp,
                months: int = 12, r: float = 0.0, mc_paths: int = 50_000) -> pd.DataFrame:
    """Value each monthly put of a floor at K under Black-76 and under the two-factor challenger.

    Black-76 uses expiry at month end (the average is known then). The challenger is priced
    analytically (the average of a Gaussian process is Gaussian) and by Monte Carlo as a cross-check.
    """
    rows = []
    for k in range(1, months + 1):
        m0 = (pricing_date + pd.offsets.MonthBegin(k)).normalize()
        m1 = m0 + pd.offsets.MonthEnd(0)
        T = (m1 - pricing_date).days / 365
        df = np.exp(-r * T)
        b76 = black76(F, K, T, sigma, r)
        # Remediation candidate: same model, but with the variance time of an average over the month
        # (a random walk averaged over days a+1..a+n has variance a + (n+1)(2n+1)/(6n) days).
        a, n_d = (m0 - pricing_date).days - 1, m1.day
        T_avg = (a + (n_d + 1) * (2 * n_d + 1) / (6 * n_d)) / 365
        b76_avg = float(np.exp(-r * T) * black76(F, K, T_avg, sigma, 0.0))
        sd = average_std(p, (m0 - pricing_date).days - 1, m1.day)
        ch = bachelier_put(F, K, sd, df)
        ch_mc, ch_se = mc_average_put(F, K, p, pricing_date, m0, r, mc_paths, seed=k)
        rows.append({"month": m0.strftime("%Y-%m"), "T_years": T, "black76": b76, "black76_avg_time": b76_avg, "challenger": ch,
                     "challenger_mc": ch_mc, "challenger_mc_se": ch_se, "challenger_avg_std": sd,
                     "black76_std_equiv": F * sigma * np.sqrt(T),
                     "challenger_implied_vol": implied_vol(ch, F, K, T, r)})
    return pd.DataFrame(rows)
