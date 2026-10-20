"""Market risk of a PPA position: daily P&L, VaR and ES models, and their backtests.

Position: the offtaker of a pay-as-produced PPA at a fixed strike. Each day it receives the
plant's output, pays the strike and values the energy at the day-ahead price, so its daily P&L is
sum over hours of g_h * (p_h - K). The plant is the national fleet profile scaled to a fixed
annual production, which removes the effect of new capacity on volumes.

VaR and ES are forecast one day ahead from a rolling window of past P&L, with three models:
historical simulation, normal with EWMA volatility (RiskMetrics, lambda 0.94) and GARCH(1,1)
with Student-t innovations; plus a remediation candidate, historical simulation conditioned on the
day type (working day vs weekend or public holiday). Losses are positive numbers (loss = -P&L).
"""

from __future__ import annotations

import numpy as np
import pandas as pd
from dateutil.easter import easter
from scipy.optimize import minimize
from scipy.special import gammaln
from scipy.stats import binom, chi2, norm, t as student_t


def daily_pnl(hourly: pd.DataFrame, tech: str, strike: float, annual_mwh: float = 100_000.0) -> pd.Series:
    """Daily P&L (EUR) of a PaP PPA offtaker for a plant producing `annual_mwh` per local year."""
    df = hourly.dropna(subset=[tech]).copy()
    df["g"] = df[tech] / df.groupby("year")[tech].transform("sum") * annual_mwh
    day = df["ts_utc"].dt.tz_convert("Europe/Berlin").dt.tz_localize(None).dt.normalize()
    pnl = (df["g"] * (df["price"] - strike)).groupby(day).sum()
    pnl.index.name = "date"
    return pnl.rename("pnl")


def is_off_day(dates: pd.DatetimeIndex) -> np.ndarray:
    """Weekend or nationwide German public holiday (fixed dates and the Easter-dependent ones)."""
    off = set()
    for y in sorted(set(dates.year)):
        e = pd.Timestamp(easter(y))
        off |= {pd.Timestamp(y, m, d) for m, d in ((1, 1), (5, 1), (10, 3), (12, 25), (12, 26))}
        off |= {e + pd.Timedelta(days=k) for k in (-2, 1, 39, 50)}  # Good Friday, Easter Monday, Ascension, Whit Monday
    return np.asarray((dates.dayofweek >= 5) | dates.normalize().isin(list(off)))


# --- VaR / ES models -------------------------------------------------------------------------

def hs_var_es(losses: np.ndarray, alpha: float, alpha_es: float) -> tuple[float, float]:
    """Historical simulation: empirical quantile, and the mean of losses at or beyond the ES quantile."""
    var = float(np.quantile(losses, alpha))
    q = np.quantile(losses, alpha_es)
    return var, float(losses[losses >= q].mean())


def ewma_sigma(x: np.ndarray, lam: float = 0.94) -> float:
    """One-step-ahead EWMA volatility of demeaned x, seeded with the sample variance."""
    e = x - x.mean()
    v = e.var()
    for r in e:
        v = lam * v + (1 - lam) * r**2
    return float(np.sqrt(v))


def normal_var_es(mu: float, sigma: float, alpha: float, alpha_es: float) -> tuple[float, float]:
    z, z_es = norm.ppf(alpha), norm.ppf(alpha_es)
    return mu + sigma * z, mu + sigma * norm.pdf(z_es) / (1 - alpha_es)


def _garch_filter(e: np.ndarray, omega: float, a: float, b: float) -> np.ndarray:
    """Conditional variances h_1..h_{n+1} of a GARCH(1,1) (the last one is the forecast)."""
    h = np.empty(len(e) + 1)
    h[0] = e.var()
    for i, r in enumerate(e):
        h[i + 1] = omega + a * r**2 + b * h[i]
    return h


def fit_garch_t(x: np.ndarray, start: np.ndarray | None = None) -> dict:
    """Maximum-likelihood GARCH(1,1) with constant mean and standardised Student-t innovations.

    Parameters are transformed so the optimiser works unconstrained: omega > 0, alpha, beta > 0 with
    alpha + beta < 1, and nu > 2.1.
    """
    scale = x.std()
    y = x / scale  # fit on unit scale for numerical stability, rescale at the end

    def unpack(th):
        mu, lw, la, lb, ln = np.clip(th, -30, 30)
        ea, eb = np.exp(la), np.exp(lb)
        a, b = ea / (1 + ea + eb), eb / (1 + ea + eb)
        return mu, np.exp(lw), a, b, 2.1 + np.exp(ln)

    def nll(th):
        mu, w, a, b, nu = unpack(th)
        e = y - mu
        h = _garch_filter(e, w, a, b)[:-1]
        z2 = e**2 / (h * (nu - 2))
        ll = (gammaln((nu + 1) / 2) - gammaln(nu / 2) - 0.5 * np.log(np.pi * (nu - 2))
              - 0.5 * np.log(h) - (nu + 1) / 2 * np.log1p(z2))
        return -ll.sum()

    th0 = start if start is not None else np.array([0.0, np.log(0.05), np.log(0.1 / 0.05), np.log(0.85 / 0.05), np.log(6.0)])
    res = minimize(nll, th0, method="Nelder-Mead", options={"maxiter": 4000, "xatol": 1e-6, "fatol": 1e-8})
    mu, w, a, b, nu = unpack(res.x)
    h_next = _garch_filter(y - mu, w, a, b)[-1]
    return {"mu": mu * scale, "omega": w * scale**2, "alpha": a, "beta": b, "nu": nu,
            "sigma_next": float(np.sqrt(h_next) * scale), "theta": res.x, "converged": bool(res.success)}


def t_var_es(mu: float, sigma: float, nu: float, alpha: float, alpha_es: float) -> tuple[float, float]:
    """VaR and ES of mu + sigma * z, z a Student-t scaled to unit variance."""
    s = np.sqrt((nu - 2) / nu)
    q, q_es = student_t.ppf(alpha, nu), student_t.ppf(alpha_es, nu)
    es_std = student_t.pdf(q_es, nu) / (1 - alpha_es) * (nu + q_es**2) / (nu - 1)
    return mu + sigma * s * q, mu + sigma * s * es_std


def rolling_forecasts(pnl: pd.Series, window: int = 365, alpha: float = 0.99, alpha_es: float = 0.975,
                      refit_every: int = 20) -> pd.DataFrame:
    """One-day-ahead VaR(alpha) and ES(alpha_es) of the loss for every day after the first window.

    Each model also reports VaR at alpha_es, which the ES backtest needs.
    """
    loss = -pnl.to_numpy()
    off = is_off_day(pd.DatetimeIndex(pnl.index))
    rows, garch, theta = [], None, None
    for i in range(window, len(loss)):
        w = loss[i - window:i]
        row = {"date": pnl.index[i], "loss": loss[i], "off_day": bool(off[i])}
        row["hs_var"], row["hs_es"] = hs_var_es(w, alpha, alpha_es)
        row["hs_var_es_level"] = float(np.quantile(w, alpha_es))
        wc = w[off[i - window:i] == off[i]]  # same day type only
        row["hs_cal_var"], row["hs_cal_es"] = hs_var_es(wc, alpha, alpha_es)
        row["hs_cal_var_es_level"] = float(np.quantile(wc, alpha_es))
        sig = ewma_sigma(w)
        row["ewma_var"], row["ewma_es"] = normal_var_es(w.mean(), sig, alpha, alpha_es)
        row["ewma_var_es_level"] = w.mean() + sig * norm.ppf(alpha_es)
        if garch is None or (i - window) % refit_every == 0:
            garch = fit_garch_t(w, theta)
            theta = garch["theta"]
        sig_g = float(np.sqrt(_garch_filter(w - garch["mu"], garch["omega"], garch["alpha"], garch["beta"])[-1]))
        row["garch_var"], row["garch_es"] = t_var_es(garch["mu"], sig_g, garch["nu"], alpha, alpha_es)
        row["garch_var_es_level"] = t_var_es(garch["mu"], sig_g, garch["nu"], alpha_es, alpha_es)[0]
        rows.append(row)
    return pd.DataFrame(rows).set_index("date")


# --- Backtests -------------------------------------------------------------------------------

def _xlogy(x: float, y: float) -> float:
    return 0.0 if x == 0 else x * np.log(y)


def kupiec_pof(hits: np.ndarray, p: float) -> tuple[float, float]:
    """Kupiec proportion-of-failures likelihood ratio and its chi-square(1) p-value."""
    n, x = len(hits), int(hits.sum())
    phat = x / n
    lr = -2 * (_xlogy(n - x, 1 - p) + _xlogy(x, p) - _xlogy(n - x, 1 - phat) - _xlogy(x, phat))
    return float(lr), float(chi2.sf(lr, 1))


def christoffersen(hits: np.ndarray, p: float) -> dict:
    """Christoffersen independence test (first-order Markov) and the conditional-coverage test."""
    h = hits.astype(int)
    prev, cur = h[:-1], h[1:]
    n00 = int(((prev == 0) & (cur == 0)).sum()); n01 = int(((prev == 0) & (cur == 1)).sum())
    n10 = int(((prev == 1) & (cur == 0)).sum()); n11 = int(((prev == 1) & (cur == 1)).sum())
    pi01 = n01 / max(n00 + n01, 1)
    pi11 = n11 / max(n10 + n11, 1)
    pi = (n01 + n11) / max(n00 + n01 + n10 + n11, 1)
    lr_ind = -2 * (_xlogy(n00 + n10, 1 - pi) + _xlogy(n01 + n11, pi)
                   - _xlogy(n00, 1 - pi01) - _xlogy(n01, pi01) - _xlogy(n10, 1 - pi11) - _xlogy(n11, pi11))
    lr_pof, _ = kupiec_pof(h, p)
    return {"n11": n11, "lr_ind": float(lr_ind), "p_ind": float(chi2.sf(lr_ind, 1)),
            "lr_cc": float(lr_pof + lr_ind), "p_cc": float(chi2.sf(lr_pof + lr_ind, 2))}


def traffic_light(exceptions: int, n: int = 250, p: float = 0.01) -> str:
    """Basel traffic-light zone from the cumulative binomial probability of the exception count.

    For n = 250 at 99% this gives the familiar bands: green 0-4, yellow 5-9, red 10 or more.
    """
    cum = binom.cdf(exceptions, n, p)
    return "green" if cum < 0.95 else ("yellow" if cum < 0.9999 else "red")


def es_exceedance_test(loss: np.ndarray, var_es_level: np.ndarray, es: np.ndarray,
                       n_boot: int = 10_000, seed: int = 0) -> tuple[int, float, float]:
    """McNeil-Frey style test: on days the loss exceeds VaR at the ES level, is loss - ES zero on average?

    One-sided bootstrap p-value against the alternative that ES underestimates the tail (mean > 0).
    Returns (number of exceedances, mean residual, p-value).
    """
    exc = loss > var_es_level
    r = (loss - es)[exc]
    if len(r) < 2:
        return int(len(r)), float(r.mean()) if len(r) else float("nan"), float("nan")
    rng = np.random.default_rng(seed)
    c = r - r.mean()
    boot = rng.choice(c, size=(n_boot, len(c)), replace=True).mean(axis=1)
    return int(len(r)), float(r.mean()), float((boot >= r.mean()).mean())


def backtest(fc: pd.DataFrame, models=("hs", "ewma", "garch", "hs_cal"), alpha: float = 0.99) -> pd.DataFrame:
    """VaR and ES backtests for each model over the whole forecast sample and the worst 250-day block."""
    p = 1 - alpha
    loss = fc["loss"].to_numpy()
    rows = []
    for m in models:
        hits = loss > fc[f"{m}_var"].to_numpy()
        lr, p_pof = kupiec_pof(hits, p)
        ch = christoffersen(hits, p)
        roll = pd.Series(hits.astype(int)).rolling(250).sum().dropna()
        n_exc, es_mean, es_p = es_exceedance_test(loss, fc[f"{m}_var_es_level"].to_numpy(), fc[f"{m}_es"].to_numpy())
        rows.append({
            "model": m, "days": len(hits), "exceptions": int(hits.sum()), "expected": len(hits) * p,
            "kupiec_p": p_pof, "christoffersen_ind_p": ch["p_ind"], "consecutive_exceptions": ch["n11"],
            "cond_coverage_p": ch["p_cc"], "zone_full_sample": traffic_light(int(hits.sum()), len(hits), p),
            "max_exceptions_250d": int(roll.max()), "zone_worst_250d": traffic_light(int(roll.max()), 250, p),
            "es_exceedances": n_exc, "es_mean_residual": es_mean, "es_test_p": es_p,
            "mean_var": float(fc[f"{m}_var"].mean()),
            "exceptions_on_off_days": int((hits & fc["off_day"].to_numpy()).sum()),
        })
    return pd.DataFrame(rows)
