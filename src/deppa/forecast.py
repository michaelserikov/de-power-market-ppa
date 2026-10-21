"""Day-ahead price forecasting for DE-LU (v0.5): naive benchmark, LEAR and gradient boosting.

Set-up follows the open benchmarks of the electricity price forecasting literature (Lago,
Marcjasz, De Schutter and Weron, 2021): forecasts for all 24 hours of day d are made with the
information of day d-1, i.e. prices up to day d-1, the TSOs' day-ahead forecasts of load and of
wind and solar generation for day d, and calendar effects. Days are local (Europe/Berlin) with 24
hours; on clock-change days the missing hour is interpolated and the doubled hour averaged.

- Naive: day d-1 prices for Tuesday to Friday, day d-7 prices for Monday, Saturday and Sunday.
- LEAR: one LASSO per hour (penalty by AIC), on asinh-transformed standardised prices, with
  prices of d-1, d-2, d-3 and d-7, load and wind+solar forecasts for d, d-1 and d-7, weekday
  dummies, the last EU allowance auction price before d and the previous month's gas price;
  recalibrated every 7 days on a rolling window of 364 or 728 days (the literature recalibrates
  daily; weekly keeps the run time short and each forecast still uses only information of d-1).
- GBM: histogram gradient boosting on all hours (hour as a feature), same information,
  recalibrated monthly.
Evaluation: MAE, RMSE, relative MAE against the naive forecast, and the Diebold-Mariano test on the
daily L1 norm of the 24 errors.
"""

from __future__ import annotations

import warnings

import numpy as np
import pandas as pd
from scipy.stats import norm
from sklearn.ensemble import HistGradientBoostingRegressor
from sklearn.exceptions import ConvergenceWarning
from sklearn.linear_model import LassoLarsIC

TZ = "Europe/Berlin"
HOURS = list(range(24))


# --- data preparation ---------------------------------------------------------------------------

def daily_matrix(df: pd.DataFrame, col: str) -> pd.DataFrame:
    """Local days x 24 local hours of one hourly column (clock-change days fixed)."""
    local = df["ts_utc"].dt.tz_convert(TZ)
    g = pd.DataFrame({"day": local.dt.tz_localize(None).dt.normalize(), "hour": local.dt.hour, "v": df[col].to_numpy()})
    m = g.groupby(["day", "hour"])["v"].mean().unstack("hour").reindex(columns=HOURS)
    return m.interpolate(axis=1, limit_direction="both")


def build_inputs(hourly: pd.DataFrame, forecasts: pd.DataFrame, eua: pd.DataFrame, gas_monthly: pd.Series) -> dict:
    """Daily matrices of price and forecasts plus the daily fuel signals known before each day."""
    df = hourly[["ts_utc", "price"]].merge(forecasts, on="ts_utc", how="left")
    df["res_fc"] = df["onshore_fc"] + df["offshore_fc"] + df["solar_fc"]
    price = daily_matrix(df, "price")
    load = daily_matrix(df, "load_fc").reindex(price.index).interpolate(limit_direction="both")
    res = daily_matrix(df, "res_fc").reindex(price.index).interpolate(limit_direction="both")
    days = price.index
    # last auction price strictly before the delivery day (an auction on d-1 is known when bidding for d)
    e = eua.sort_values("date").assign(known_from=lambda x: (x["date"] + pd.Timedelta(days=1)).astype("datetime64[ns]"))
    left = pd.DataFrame({"day": days.astype("datetime64[ns]")})
    eua_known = pd.merge_asof(left, e[["known_from", "price"]], left_on="day", right_on="known_from",
                              direction="backward")["price"].set_axis(days)
    # previous month's average gas price (published after the month ends)
    prev = (days.to_period("M") - 1)
    gas = pd.Series(gas_monthly.reindex(prev).to_numpy(), index=days)
    return {"price": price, "load": load, "res": res, "eua": eua_known, "gas": gas}


# --- naive -------------------------------------------------------------------------------------------

def naive(price: pd.DataFrame, days: pd.DatetimeIndex) -> pd.DataFrame:
    out = []
    for d in days:
        lag = 7 if d.dayofweek in (0, 5, 6) else 1
        out.append(price.loc[d - pd.Timedelta(days=lag)].to_numpy())
    return pd.DataFrame(out, index=days, columns=HOURS)


# --- LEAR --------------------------------------------------------------------------------------------

def _features(inp: dict, days: pd.DatetimeIndex) -> np.ndarray:
    """Feature matrix for the given target days (raw, untransformed)."""
    p, ld, rs = inp["price"], inp["load"], inp["res"]
    blocks = []
    for lag in (1, 2, 3, 7):
        blocks.append(p.reindex(days - pd.Timedelta(days=lag)).to_numpy())
    for m in (ld, rs):
        for lag in (0, 1, 7):
            blocks.append(m.reindex(days - pd.Timedelta(days=lag)).to_numpy())
    dow = np.zeros((len(days), 7))
    dow[np.arange(len(days)), days.dayofweek] = 1
    blocks.append(dow)
    blocks.append(inp["eua"].reindex(days).to_numpy()[:, None])
    blocks.append(inp["gas"].reindex(days).to_numpy()[:, None])
    return np.hstack(blocks)


N_PRICE_FEATURES = 4 * 24


def _asinh_fit(x: np.ndarray) -> tuple[float, float]:
    med = float(np.median(x))
    mad = float(np.median(np.abs(x - med))) * 1.4826
    return med, mad if mad > 0 else 1.0


def _lear_fit(inp: dict, start: pd.Timestamp, window: int):
    """Fit the 24 hourly LASSO models on the `window` days before `start`; returns a predictor."""
    cal = pd.date_range(start - pd.Timedelta(days=window), start - pd.Timedelta(days=1), freq="D")
    X = _features(inp, cal)
    Y = inp["price"].reindex(cal).to_numpy()
    ok = ~np.isnan(X).any(axis=1) & ~np.isnan(Y).any(axis=1)
    X, Y = X[ok], Y[ok]
    med, mad = _asinh_fit(Y.ravel())
    tp = lambda a: np.arcsinh((a - med) / mad)  # noqa: E731  same transform for target and lagged prices
    exo = slice(N_PRICE_FEATURES, None)
    Xt = X.copy()
    Xt[:, :N_PRICE_FEATURES] = tp(X[:, :N_PRICE_FEATURES])
    mu, sd = Xt[:, exo].mean(axis=0), Xt[:, exo].std(axis=0)
    sd[sd == 0] = 1.0
    Xt[:, exo] = (Xt[:, exo] - mu) / sd
    Yt = tp(Y)
    models = []
    with warnings.catch_warnings():
        warnings.simplefilter("ignore", ConvergenceWarning)
        for h in HOURS:
            models.append(LassoLarsIC(criterion="aic", max_iter=2500).fit(Xt, Yt[:, h]))

    def predict(days: pd.DatetimeIndex) -> np.ndarray:
        Xd = _features(inp, days)
        Xd[:, :N_PRICE_FEATURES] = tp(Xd[:, :N_PRICE_FEATURES])
        Xd[:, exo] = (Xd[:, exo] - mu) / sd
        return np.sinh(np.column_stack([m.predict(Xd) for m in models])) * mad + med

    return predict


def lear(inp: dict, days: pd.DatetimeIndex, window: int, recal_days: int = 7) -> pd.DataFrame:
    """LEAR forecasts; models recalibrated every `recal_days` days on the window before each block."""
    out = []
    for i in range(0, len(days), recal_days):
        block = days[i:i + recal_days]
        out.append(_lear_fit(inp, block[0], window)(block))
    return pd.DataFrame(np.vstack(out), index=days, columns=HOURS)


# --- gradient boosting -------------------------------------------------------------------------------

def _long_features(inp: dict, days: pd.DatetimeIndex) -> pd.DataFrame:
    p, ld, rs = inp["price"], inp["load"], inp["res"]
    rows = []
    for h in HOURS:
        f = pd.DataFrame(index=days)
        f["hour"] = h
        f["dow"] = days.dayofweek
        f["month"] = days.month
        for lag in (1, 2, 7):
            f[f"p_lag{lag}"] = p[h].reindex(days - pd.Timedelta(days=lag)).to_numpy()
        prev = p.reindex(days - pd.Timedelta(days=1))
        f["p1_mean"], f["p1_min"], f["p1_max"] = prev.mean(axis=1).to_numpy(), prev.min(axis=1).to_numpy(), prev.max(axis=1).to_numpy()
        f["load_fc"], f["res_fc"] = ld[h].reindex(days).to_numpy(), rs[h].reindex(days).to_numpy()
        f["resid_fc"] = f["load_fc"] - f["res_fc"]
        f["res_share"] = f["res_fc"] / f["load_fc"]
        f["res_fc_day"] = rs.reindex(days).mean(axis=1).to_numpy()
        f["load_fc_lag1"] = ld[h].reindex(days - pd.Timedelta(days=1)).to_numpy()
        f["res_fc_lag1"] = rs[h].reindex(days - pd.Timedelta(days=1)).to_numpy()
        f["eua"], f["gas"] = inp["eua"].reindex(days).to_numpy(), inp["gas"].reindex(days).to_numpy()
        rows.append(f.assign(day=days))
    return pd.concat(rows, ignore_index=True)


def gbm(inp: dict, days: pd.DatetimeIndex, window: int = 728, seed: int = 0) -> pd.DataFrame:
    """Monthly recalibrated gradient boosting; each month is forecast with a model trained before it."""
    out = pd.DataFrame(index=days, columns=HOURS, dtype=float)
    for month, mdays in pd.Series(days, index=days).groupby(days.to_period("M")):
        first = mdays.iloc[0]
        cal = pd.date_range(first - pd.Timedelta(days=window), first - pd.Timedelta(days=1), freq="D")
        tr = _long_features(inp, cal)
        y = inp["price"].reindex(cal).to_numpy().T.ravel()  # same order as the long features: hour-major
        ok = ~np.isnan(y)
        med, mad = _asinh_fit(y[ok])
        model = HistGradientBoostingRegressor(max_iter=400, learning_rate=0.05, max_leaf_nodes=31,
                                              categorical_features=[0, 1], random_state=seed)
        X = tr.drop(columns="day")
        model.fit(X[ok], np.arcsinh((y[ok] - med) / mad))
        te = _long_features(inp, pd.DatetimeIndex(mdays.to_numpy()))
        pred = np.sinh(model.predict(te.drop(columns="day"))) * mad + med
        te["pred"] = pred
        out.loc[te["day"].unique()] = te.pivot(index="day", columns="hour", values="pred").to_numpy()
    return out.astype(float)


# --- evaluation --------------------------------------------------------------------------------------

def metrics(actual: pd.DataFrame, fc: pd.DataFrame, naive_fc: pd.DataFrame) -> dict:
    e = (fc - actual).to_numpy()
    en = (naive_fc - actual).to_numpy()
    return {"mae": float(np.abs(e).mean()), "rmse": float(np.sqrt((e ** 2).mean())),
            "rmae": float(np.abs(e).mean() / np.abs(en).mean()), "bias": float(e.mean())}


def dm_test(actual: pd.DataFrame, fc_a: pd.DataFrame, fc_b: pd.DataFrame) -> tuple[float, float]:
    """Diebold-Mariano on the daily L1 norm of errors; one-sided p-value for H1: forecast b is more accurate than a."""
    la = (fc_a - actual).abs().sum(axis=1)
    lb = (fc_b - actual).abs().sum(axis=1)
    d = (la - lb).to_numpy()
    stat = d.mean() / (d.std(ddof=1) / np.sqrt(len(d)))
    return float(stat), float(1 - norm.cdf(stat))
