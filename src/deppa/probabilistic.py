"""Probabilistic price forecasts and the value of forecasts for a battery (v0.6).

Probabilistic forecasts turn the v0.5 point forecasts into predictive quantiles:
- Quantile Regression Averaging (QRA, Nowotarski and Weron): for each quantile level, a linear
  quantile regression of the price on the point forecasts of LEAR and gradient boosting,
  calibrated on the previous 182 days and recalibrated monthly (pooled over hours).
- Historical-simulation benchmark: the point forecast plus the empirical quantiles of its own
  errors in the same hour over the previous 182 days.
Scores: pinball loss averaged over 19 levels (5% to 95%; twice this average approximates the
CRPS), coverage of the central 80% and 90% intervals and the Kupiec test of that coverage.

Value of forecasts: the v0.3 battery (1 MW / 2 MWh) is scheduled on a forecast and settled at
the actual prices; its profit relative to scheduling on the actual prices measures what a
forecast is worth to a storage operator.
"""

from __future__ import annotations

import numpy as np
import pandas as pd
from sklearn.linear_model import QuantileRegressor

from . import risk, storage as st

LEVELS = np.round(np.arange(0.05, 0.96, 0.05), 2)
WINDOW = 182


def _long(df: pd.DataFrame) -> np.ndarray:
    return df.to_numpy().ravel()


def qra(actual: pd.DataFrame, point: dict[str, pd.DataFrame], days: pd.DatetimeIndex,
        window: int = WINDOW, levels=LEVELS) -> dict[float, pd.DataFrame]:
    """QRA quantile forecasts for `days`, monthly recalibrated on the preceding `window` days."""
    out = {q: pd.DataFrame(index=days, columns=range(24), dtype=float) for q in levels}
    names = list(point)
    for _, mdays in pd.Series(days, index=days).groupby(days.to_period("M")):
        first = mdays.iloc[0]
        cal = pd.date_range(first - pd.Timedelta(days=window), first - pd.Timedelta(days=1), freq="D")
        X = np.column_stack([_long(point[n].loc[cal]) for n in names])
        y = _long(actual.loc[cal])
        Xt = np.column_stack([_long(point[n].loc[mdays]) for n in names])
        for q in levels:
            m = QuantileRegressor(quantile=q, alpha=0.0, solver="highs").fit(X, y)
            out[q].loc[mdays] = m.predict(Xt).reshape(len(mdays), 24)
    return _sort_quantiles(out)


def historical_errors(actual: pd.DataFrame, point: pd.DataFrame, days: pd.DatetimeIndex,
                      window: int = WINDOW, levels=LEVELS) -> dict[float, pd.DataFrame]:
    """Point forecast + empirical error quantiles of the same hour over the preceding `window` days."""
    err = actual - point
    out = {q: pd.DataFrame(index=days, columns=range(24), dtype=float) for q in levels}
    for d in days:
        e = err.loc[d - pd.Timedelta(days=window):d - pd.Timedelta(days=1)]
        qs = e.quantile(list(levels))
        for q in levels:
            out[q].loc[d] = point.loc[d].to_numpy() + qs.loc[q].to_numpy()
    return out


def _sort_quantiles(qf: dict[float, pd.DataFrame]) -> dict[float, pd.DataFrame]:
    """Rearrange crossing quantiles (sort across levels) so the predictive distribution is monotone."""
    levels = sorted(qf)
    stack = np.sort(np.stack([qf[q].to_numpy() for q in levels]), axis=0)
    return {q: pd.DataFrame(stack[i], index=qf[q].index, columns=qf[q].columns) for i, q in enumerate(levels)}


def pinball(actual: pd.DataFrame, qf: dict[float, pd.DataFrame]) -> float:
    """Average pinball loss over all levels, hours and days."""
    losses = []
    for q, f in qf.items():
        d = actual.to_numpy() - f.to_numpy()
        losses.append(np.maximum(q * d, (q - 1) * d).mean())
    return float(np.mean(losses))


def coverage(actual: pd.DataFrame, qf: dict[float, pd.DataFrame], central: float) -> dict:
    """Empirical coverage of the central interval and the Kupiec test of the miss rate."""
    lo, hi = round((1 - central) / 2, 2), round(1 - (1 - central) / 2, 2)
    a = actual.to_numpy().ravel()
    inside = (a >= qf[lo].to_numpy().ravel()) & (a <= qf[hi].to_numpy().ravel())
    lr, p = risk.kupiec_pof(~inside, 1 - central)
    return {"nominal": central, "coverage": float(inside.mean()), "kupiec_p": p,
            "mean_width": float((qf[hi] - qf[lo]).to_numpy().mean())}


def battery_value(actual: pd.DataFrame, schedules_from: dict[str, pd.DataFrame], b: st.Battery = st.Battery()) -> pd.DataFrame:
    """Profit of the battery scheduled on each forecast and settled at actual prices, per day."""
    rows = []
    for d in actual.index:
        a = actual.loc[d].to_numpy()
        row = {"date": d, "perfect": st.schedule(a, b)["profit"]}
        for name, f in schedules_from.items():
            s = st.schedule(f.loc[d].to_numpy(), b)
            row[name] = st.settle(a, s["charge"], s["discharge"], b)
        rows.append(row)
    return pd.DataFrame(rows).set_index("date")
