"""Time-series econometrics of the German power price and the errors of renewable forecasts (v0.7).

1. Fuel pass-through. Monthly baseload power, TTF gas and EU allowance prices: unit-root tests
   (ADF, null of a unit root; KPSS, null of stationarity), Engle-Granger and Johansen cointegration,
   and a long-run regression power = a + b gas + c CO2 whose slopes can be read against the
   marginal cost of a gas plant (b about 1/efficiency, c about emission factor/efficiency).
   A VAR in monthly log changes gives Granger causality and impulse responses.
2. Wind and solar forecast errors. Hourly TSO day-ahead forecasts against actual generation:
   bias and mean absolute error by year and hour, and a price-equivalent of the error from the
   slope of the day-ahead price in the residual-load forecast (within month, ordinary least
   squares with monthly fixed effects).
"""

from __future__ import annotations

import warnings

import numpy as np
import pandas as pd
import statsmodels.api as sm
from statsmodels.tsa.api import VAR
from statsmodels.tsa.stattools import adfuller, coint, kpss
from statsmodels.tsa.vector_ar.vecm import coint_johansen


def unit_roots(series: dict[str, pd.Series]) -> pd.DataFrame:
    """ADF and KPSS p-values for levels and first differences."""
    rows = []
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")      # KPSS warns when the p-value is outside its table
        for name, s in series.items():
            for form, x in (("level", s), ("difference", s.diff().dropna())):
                rows.append({"series": name, "form": form, "adf_p": float(adfuller(x, autolag="AIC")[1]),
                             "kpss_p": float(kpss(x, regression="c", nlags="auto")[1])})
    return pd.DataFrame(rows)


def long_run(power: pd.Series, gas: pd.Series, co2: pd.Series) -> dict:
    """OLS power = a + b gas + c CO2 (levels, HAC errors), Engle-Granger and Johansen tests."""
    X = sm.add_constant(pd.concat({"gas": gas, "co2": co2}, axis=1))
    ols = sm.OLS(power, X).fit(cov_type="HAC", cov_kwds={"maxlags": 3})
    eg_stat, eg_p, _ = coint(power, X[["gas", "co2"]])
    jo = coint_johansen(pd.concat([power, gas, co2], axis=1).to_numpy(), det_order=0, k_ar_diff=1)
    return {"const": float(ols.params["const"]), "b_gas": float(ols.params["gas"]), "c_co2": float(ols.params["co2"]),
            "se_gas": float(ols.bse["gas"]), "se_co2": float(ols.bse["co2"]), "r2": float(ols.rsquared),
            "engle_granger_stat": float(eg_stat), "engle_granger_p": float(eg_p),
            "johansen_trace": jo.lr1.round(3).tolist(), "johansen_crit_95": jo.cvt[:, 1].round(3).tolist(),
            "johansen_rank_95": int((jo.lr1 > jo.cvt[:, 1]).sum())}


def var_analysis(df: pd.DataFrame, maxlags: int = 4, horizon: int = 6) -> dict:
    """VAR in log differences: lag order by AIC, Granger causality into power, orthogonalised IRFs."""
    d = np.log(df).diff().dropna()
    res = VAR(d).fit(maxlags=maxlags, ic="aic")
    if res.k_ar == 0:            # AIC may choose no lags; keep one so causality and IRFs are defined
        res = VAR(d).fit(1)
    lag = res.k_ar
    granger = {c: float(res.test_causality("power", [c], kind="f").pvalue) for c in df.columns if c != "power"}
    irf = res.irf(horizon)
    resp = {c: irf.orth_irfs[:, list(d.columns).index("power"), list(d.columns).index(c)].round(4).tolist()
            for c in df.columns}
    return {"lag_order": lag, "granger_p_into_power": granger, "irf_power_to_shock": resp}


def forecast_errors(df: pd.DataFrame) -> pd.DataFrame:
    """Per year: bias and MAE of wind (onshore + offshore) and solar forecasts, absolute and relative to mean output."""
    d = df.assign(wind=df["wind_onshore"] + df["wind_offshore"], wind_fc=df["onshore_fc"] + df["offshore_fc"])
    rows = []
    for y, g in d.groupby("year"):
        for tech, fc_col in (("wind", "wind_fc"), ("solar", "solar_fc")):
            e = (g[fc_col] - g[tech]).dropna()
            rows.append({"year": y, "tech": tech, "bias_mw": float(e.mean()), "mae_mw": float(e.abs().mean()),
                         "mean_output_mw": float(g[tech].mean()),
                         "nmae": float(e.abs().mean() / g[tech].mean())})
    return pd.DataFrame(rows)


def price_slope(df: pd.DataFrame) -> dict:
    """Day-ahead price on the residual-load forecast (GW) with month fixed effects; per year."""
    d = df.assign(resid_fc_gw=(df["load_fc"] - df["onshore_fc"] - df["offshore_fc"] - df["solar_fc"]) / 1000,
                  ym=df["year"].astype(str) + "-" + df["month"].astype(str)).dropna(subset=["price"])
    out = {}
    for y, g in d.dropna(subset=["resid_fc_gw"]).groupby("year"):
        X = pd.get_dummies(g["ym"], drop_first=False, dtype=float)
        X["resid_fc_gw"] = g["resid_fc_gw"]
        m = sm.OLS(g["price"], X).fit(cov_type="HAC", cov_kwds={"maxlags": 24})
        out[int(y)] = {"slope_eur_mwh_per_gw": float(m.params["resid_fc_gw"]), "se": float(m.bse["resid_fc_gw"])}
    return out
