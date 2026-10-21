# German power market: price forecasting, merit-order price model, capture prices, PPA valuation, model validation and battery arbitrage (v0.8)

[![tests](https://github.com/michaelserikov/de-power-market-ppa/actions/workflows/tests.yml/badge.svg)](https://github.com/michaelserikov/de-power-market-ppa/actions/workflows/tests.yml)

What is a MWh of wind or solar power actually worth on the German day-ahead market, and what does that mean for a power purchase agreement (PPA)? This project answers that from hourly market data for 2023 to 2025 (bidding zone DE-LU, 26,304 hours, no gaps): capture prices and capture rates, the cost of negative prices, the fair strike of a pay-as-produced PPA, the shape cost of a baseload PPA and the month-to-month risk an offtaker carries.

**Main findings**
- Solar cannibalises its own price. The solar capture rate fell from 76% (2023) to 59% (2024) and 52% (2025), while wind onshore stayed at 82-87% and wind offshore at 91-96%. Across months, each additional percentage point of solar in the load lowers the solar capture rate by about 2.1 points.
- The fair pay-as-produced strike for solar dropped from 72 EUR/MWh (2023) to 46 EUR/MWh (2024 and 2025). A solar PPA priced on 2023 data would have overpaid by about 26 EUR/MWh in the following two years.
- Negative prices matter mostly for solar: 24% of 2025 solar output fell into negative-price hours. A plant that stops producing in those hours would have raised its 2025 capture price from 46 to 65 EUR/MWh.
- Selling solar as a baseload product carries a growing shape cost: 23 EUR/MWh in 2023, 32 in 2024 and 43 in 2025 (24%, 41% and 48% of the baseload price).

**v0.2: market risk and model validation** ([full report](reports/model_validation_report.md))
- A Black-76 model for a 12-month PPA price floor (60 EUR/MWh on the monthly average price) was validated like a bank's front-office model: independent Monte Carlo replication (30 prices, all within 1.7 standard errors), analytic Greeks against finite differences (relative error 3e-8), a challenger model calibrated on daily prices and a sensitivity ladder.
- Main valuation finding: the model ignores that the floor settles on a monthly average and overstates its value by 11.7% under its own assumptions. A two-factor challenger points the same way (Black-76 32% higher), but its level/noise split is not identified from three years of spot data, so the volatility input needs market data (EEX futures or options).
- One-day VaR(99%) and ES(97.5%) of a PPA offtaker were backtested over 731 days (Kupiec, Christoffersen, Basel traffic light, ES exceedance test). Normal-EWMA and GARCH(1,1)-t models land in the red zone (19-30 exceptions against 7.3 expected), with solar exceptions almost all on weekends and holidays; historical simulation passes coverage, and conditioning it on the day type fixes the wind position but not solar.

**v0.8: battery scheduling under price uncertainty (stochastic programming, EVPI, VSS, CVaR)**
- A battery that must fix tomorrow's schedule before the auction, facing 182 price scenarios (the forecast plus its past 24-hour error vectors), gains nothing from stochastic optimisation if it is risk-neutral: the value of the stochastic solution (VSS) is exactly zero, because profit is linear in prices and the mean-price schedule is optimal. The value of perfect information (EVPI) is about 27 EUR per day (around 10,000 EUR per MW and year within the scenario model).
- Stochastic optimisation pays once risk matters. Weighting the expected profit against CVaR (the mean of the worst 10% of scenarios), VSS rises to 12 EUR per day at full risk aversion, and the risk-return frontier shows the trade: CVaR improves by 13% for 7% lower expected profit.
- At actual prices (July 2024 to December 2025) a mild risk weight keeps the realised profit (69.7 vs 69.6 thousand EUR per MW and year) while cutting loss days from 8 to 5 and the worst day from -49 to -40 EUR; full risk aversion halves the worst day but costs 5% of profit, mostly by leaving the battery idle on about 6% of days.

**v0.7: econometrics of fuel pass-through and of renewable forecast errors**
- Monthly power, gas and carbon prices (2020-2025) are non-stationary but cointegrated (Engle-Granger p < 0.001, Johansen rank 1): in the long run the baseload price is about 4.0 + 1.59 x gas + 0.32 x CO2 (R2 0.95). The slopes are below those of a gas plant that always sets the price (about 2 and 0.4), as expected when renewables and coal set it in part of the hours.
- The TSOs' day-ahead wind and solar forecasts miss by 1.36 GW on average in 2019 and 1.70 GW in 2025 as capacity grows, while the price has become three times more sensitive to residual load (about 1.1 to 3.2 EUR/MWh per GW): the price equivalent of forecast errors rose from about 1.5 to 5.4 EUR/MWh.

**v0.6: probabilistic forecasts and what forecasts are worth**
- A battery scheduled on the point forecast captures 94% (2024) and 95% (2025) of the profit it would make with perfect knowledge of the next day's prices, against 76-80% when it simply repeats yesterday's prices: in 2025 the forecast is worth about 10,800 EUR per MW of a 2-hour battery (69.0 vs 58.2 thousand EUR per MW).
- Predictive intervals from quantile regression averaging (QRA) are slightly too narrow (the central 80% interval covers 77% of prices, the 90% interval 88%), and a simple benchmark that adds past errors of the same hour scores as well (pinball loss 4.9 vs 5.0); in 2025 the 80% intervals of both methods pass the Kupiec coverage test.

**v0.5: day-ahead price forecasting**
- Forecasting all 24 hourly prices of the next day with the information available the day before, an average of a LEAR model (hourly LASSO regressions, the standard benchmark of the price-forecasting literature) and a gradient-boosting model has a mean absolute error of 12.0 EUR/MWh over 2024-2025 out of sample, 44% of the error of the naive forecast (27.4 EUR/MWh). The average is significantly more accurate than each model alone (Diebold-Mariano, p < 0.001).
- Errors are largest in the evening peak (18:00-20:00) and in sunny weekend hours when prices fall deeply negative; no model sees the deepest negative spikes coming.

**v0.4: merit-order dispatch model**
- A merit-order model of the German lignite, hard-coal and gas fleet, driven by monthly fuel and carbon prices from open sources (World Bank, ECB, EEX auctions), reproduces the hourly day-ahead price with a correlation of 0.71 to 0.74 (daily means 0.82 to 0.85) and a mean absolute error of 20 to 23 EUR/MWh. Two parameters are calibrated on 2023 only; 2024 and 2025 are out of sample, with errors of the same size as in the calibration year.
- The model dispatches hard coal within 7% of the observed annual output, but runs lignite 12 to 15% too much and gas 12 to 15% too little: part of the gas fleet runs for heat or system services regardless of the price, which a cost-only merit order does not see.
- What it misses is the tails: it cannot produce negative prices or scarcity spikes, and in 12 to 13% of hours its price drops to zero where actual prices fall gradually (4 to 8% of hours at or below zero). These hours are set by exports, flexibility and bidding behaviour, the next things to model.

**v0.3: battery day-ahead arbitrage**
- A 1 MW battery scheduled optimally on each day's day-ahead prices (88% round trip, 10 EUR/MWh degradation cost) earned 52, 63 and 72 thousand EUR per MW in 2023, 2024 and 2025 with 2 hours of storage, and 29 to 40 (1 hour) or 79 to 114 (4 hours) thousand EUR per MW. Revenue grew by about 40% in two years for every duration.
- The reason is wider daily spreads: the mean gap between the two most and the two least expensive hours rose from 92 to 104 and 116 EUR/MWh, and hours with negative prices from 301 to 457 and 573. Across months, each additional percentage point of solar in the load widens the spread by about 2.2 EUR/MWh. Solar cannibalises its own capture price (v0.1) but feeds storage.
- Longer storage earns more per MW but less per MWh of capacity (2025: 40 thousand EUR per MWh for 1 hour, 28 for 4 hours). A naive schedule built from yesterday's prices captures 71 to 81% of the optimal profit, so knowing the day's prices is worth about a fifth of the revenue.

## Results

Yearly capture prices (EUR/MWh) and capture rates:

| Year | Baseload | Wind onshore | Wind offshore | Solar | Hours with negative price | Solar output at negative price |
|---|---|---|---|---|---|---|
| 2023 | 95.2 | 78.6 (83%) | 86.6 (91%) | 72.2 (76%) | 3.4% | 8.3% |
| 2024 | 78.5 | 64.6 (82%) | 71.4 (91%) | 46.2 (59%) | 5.2% | 18.4% |
| 2025 | 89.3 | 77.3 (87%) | 85.5 (96%) | 46.1 (52%) | 6.5% | 24.1% |

![Capture rates](figures/capture_rates.png)

![Monthly prices](figures/monthly_prices.png)

![Solar cannibalisation](figures/solar_cannibalisation.png)

**PPA valuation.** For a pay-as-produced (PaP) PPA the fair strike over 2023-2025 equals the capture price of the period: 73.5 EUR/MWh for wind onshore, 81.0 for wind offshore and 53.6 for solar. At that strike, the offtaker's result per MWh in a single month ranges (10th to 90th percentile) from -18 to +18 EUR/MWh for onshore wind, -22 to +20 for offshore wind and -19 to +58 for solar. Solar's spread is the widest because summer months, with most of the output, are also the months with the lowest capture prices.

![PaP offtaker risk](figures/pap_offtaker_risk.png)

Shape cost of a baseload PPA (baseload price minus capture price, EUR/MWh):

| Year | Wind onshore | Wind offshore | Solar |
|---|---|---|---|
| 2023 | 16.6 | 8.6 | 23.0 |
| 2024 | 14.0 | 7.1 | 32.3 |
| 2025 | 12.0 | 3.8 | 43.3 |

All numbers are written by the pipeline to `results/` (`capture_prices_yearly.csv`, `capture_prices_monthly.csv`, `baseload_profile_cost.csv`, `pap_monthly_offtaker.csv`, `summary.json`).

## v0.2: model validation and market risk

![Floor valuation](figures/floor_strip.png)

| Floor value, 12 monthly puts (EUR/MWh-month) | |
|---|---|
| Black-76, expiry at month end (model under validation) | 30.19 |
| Black-76, variance time of a monthly average | 26.66 |
| Two-factor challenger (random-walk level + mean-reverting daily deviation, arithmetic) | 22.81 |

![VaR backtest](figures/var_backtest.png)

| Position | Model | Exceptions (expected 7.3) | Kupiec p | Independence p | Zone, full / worst 250 days |
|---|---|---|---|---|---|
| Solar | Historical simulation | 10 | 0.34 | 0.60 | green / yellow |
| Solar | Normal, EWMA vol | 21 | <0.001 | <0.001 | red / red |
| Solar | GARCH(1,1)-t | 19 | <0.001 | 0.51 | red / red |
| Solar | HS by day type | 14 | 0.03 | <0.001 | yellow / yellow |
| Wind onshore | Historical simulation | 10 | 0.34 | <0.001 | green / yellow |
| Wind onshore | Normal, EWMA vol | 30 | <0.001 | 0.04 | red / red |
| Wind onshore | GARCH(1,1)-t | 24 | <0.001 | 0.20 | red / red |
| Wind onshore | HS by day type | 11 | 0.20 | 0.15 | green / yellow |

Method, findings with severity and recommendations: [reports/model_validation_report.md](reports/model_validation_report.md). Outputs: `results/validation/` (replication, Greeks, sensitivity, floor strip, VaR/ES forecasts, backtests, `summary.json`).

**Methods in short.** Black-76 with analytic Greeks; antithetic Monte Carlo; implied volatility by root finding; a two-factor arithmetic price model (Schwartz-Smith type split into a random-walk level and an AR(1) deviation, weekday effects) priced in closed form (Bachelier on the monthly average) and by simulation. VaR/ES by historical simulation, normal with EWMA volatility (RiskMetrics, lambda 0.94) and GARCH(1,1) with Student-t innovations (maximum likelihood, own implementation), on a 365-day rolling window. Backtests: Kupiec proportion of failures, Christoffersen independence and conditional coverage, Basel traffic light from binomial probabilities, and a bootstrap ES exceedance test.

## v0.8: battery scheduling under price uncertainty

![EVPI and VSS](figures/stochastic_evpi_vss.png)

| Risk weight lambda | WS | RP | EEV | EVPI | VSS | Expected profit | CVaR 10% | Realised profit, EUR per MW and year | Worst day | Loss days | MWh discharged per day |
|---|---|---|---|---|---|---|---|---|---|---|---|
| 0 (risk-neutral) | 214.9 | 187.5 | 187.5 | 27.4 | 0.0 | 187.5 | 91.1 | 69,557 | -49 | 8 | 3.21 |
| 0.25 | 193.7 | 164.0 | 163.4 | 29.7 | 0.6 | 186.8 | 95.7 | 69,718 | -40 | 5 | 3.08 |
| 0.5 | 172.6 | 142.0 | 139.3 | 30.5 | 2.7 | 184.4 | 99.6 | 69,228 | -36 | 5 | 2.92 |
| 0.75 | 151.4 | 121.7 | 115.2 | 29.7 | 6.4 | 180.0 | 102.2 | 67,826 | -29 | 4 | 2.72 |
| 1 (CVaR only) | 130.2 | 102.9 | 91.1 | 27.2 | 11.8 | 174.8 | 102.9 | 66,204 | -26 | 3 | 2.57 |

EUR per day unless stated, mean over 549 days (1 July 2024 to 31 December 2025), 1 MW / 2 MWh battery. WS, RP, EEV, EVPI and VSS are in units of the risk-weighted objective (1 - lambda) E[profit] + lambda CVaR. Perfect knowledge of each day's prices would have earned 74,042 EUR per MW and year.

![Frontier](figures/stochastic_frontier.png)

![Realised tail](figures/stochastic_realised_tail.png)

The ex-ante EVPI (27 EUR per day, about 10,000 EUR per MW and year) is larger than the realised gap between the risk-neutral schedule and perfect foresight (12 EUR per day, 4,500 EUR per MW and year): the scenario set, built from half a year of past errors, is wider than the errors actually made in this period.

**Method.** Two-stage view of one day: the schedule (hourly charge and discharge, 1 MW, 2 MWh, 88% round trip, 10 EUR/MWh degradation, half full at midnight, no simultaneous charge and discharge) is chosen before prices are known and evaluated in 182 scenarios = the v0.5 LEAR + boosting forecast for the day plus the 24-hour error vectors of that forecast on each of the previous 182 days. Objective (1 - lambda) E[profit] + lambda CVaR_10%[profit], with CVaR linearised after Rockafellar and Uryasev, solved as a mixed-integer linear program (SciPy/HiGHS) per day. WS solves each scenario with perfect knowledge; EEV evaluates the schedule optimised on the mean scenario; EVPI = WS - RP and VSS = RP - EEV (Birge and Louveaux). The tests check VSS = 0 for lambda = 0 and WS >= RP >= EEV. Realised profit settles each schedule at the actual prices.

**Limitations.** The battery commits a fixed schedule; real day-ahead bids can be price-dependent, which itself hedges part of the risk, and intraday re-trading would add recourse that is not modelled here. Scenarios come from past forecast errors, not from a fitted probabilistic model, and are equally weighted.

## v0.7: econometrics of fuel pass-through and of renewable forecast errors

![Pass-through](figures/econometrics_passthrough.png)

| Test (monthly, Jan 2020 to Dec 2025, 72 months) | Power | Gas | CO2 |
|---|---|---|---|
| ADF p, level (null: unit root) | 0.31 | 0.36 | 0.44 |
| ADF p, first difference | < 0.001 | < 0.001 | < 0.001 |
| KPSS p, level (null: stationary) | > 0.10 | > 0.10 | 0.01 |

The ADF tests do not reject a unit root in levels but reject it in differences; KPSS rejects stationarity only for CO2, so the evidence for power and gas rests on ADF, with the low power of 72 months in mind.

| Long-run relation power = a + b gas + c CO2 | a | b (gas) | c (CO2) | R2 | Engle-Granger p | Johansen rank (95%) |
|---|---|---|---|---|---|---|
| 2020-2025 | 4.0 | 1.59 (0.09) | 0.32 (0.10) | 0.95 | < 0.001 | 1 |
| 2023-2025 | -15.5 | 1.42 (0.35) | 0.68 (0.20) | 0.67 | 0.03 | 0 |

HAC standard errors in brackets. A gas plant at the margin in every hour would give b = 1/efficiency (about 2.0 at 50%) and c = emission factor/efficiency (about 0.40): the estimates sit below, consistent with gas setting the price in only part of the hours. After the crisis the gas slope is less precise and carbon matters more, and with 36 months the Johansen test no longer finds a cointegrating relation. A VAR(1) in monthly log changes (lag chosen by AIC): carbon Granger-causes power (p = 0.02), gas at the 10% level (p = 0.07); a gas-price shock raises the power price within one month.

![Forecast errors](figures/res_forecast_errors.png)

| Year | Wind forecast MAE, GW (% of mean output) | Solar forecast MAE, GW (%) | Price slope, EUR/MWh per GW of residual load | Price equivalent of wind+solar error, EUR/MWh |
|---|---|---|---|---|
| 2019 | 1.22 (8.6%) | 0.33 (7.0%) | 1.1 | 1.5 |
| 2021 | 1.17 (9.0%) | 0.37 (7.1%) | 3.1 | 4.0 |
| 2022 | 1.22 (8.5%) | 0.43 (6.7%) | 7.1 | 10.0 |
| 2023 | 1.39 (8.5%) | 0.44 (6.9%) | 3.0 | 4.7 |
| 2024 | 1.39 (8.8%) | 0.57 (7.9%) | 3.0 | 4.9 |
| 2025 | 1.38 (9.1%) | 0.68 (8.0%) | 3.2 | 5.4 |

Wind errors grow through the day (1.1 GW at night to 1.55 GW in the evening) because the forecast horizon gets longer; solar errors peak at noon.

**Method.** Monthly means of the hourly day-ahead price; TTF gas and EUA prices as in v0.4. Unit roots: ADF (lag by AIC) and KPSS (statsmodels, whose KPSS p-values are bounded at 0.01 and 0.10). Long run: OLS in levels with HAC errors (3 lags), Engle-Granger and Johansen (constant, one lagged difference). VAR in log differences, lag by AIC up to 4, orthogonalised impulse responses. Forecast errors: hourly TSO day-ahead forecast minus actual generation. Price slope: OLS of the hourly price on the residual-load forecast (load minus wind and solar forecasts) with month fixed effects and HAC errors, per year; the price equivalent multiplies the mean absolute wind+solar error by this slope. It is a sensitivity, not the cost actually paid, which would need intraday and imbalance prices.


![Fan chart](figures/forecast_fan_chart.png)

| Method (July 2024 to December 2025) | Pinball loss | 80% interval: coverage (Kupiec p) | 90% interval: coverage (Kupiec p) | Mean width of 80% interval |
|---|---|---|---|---|
| QRA on LEAR and gradient boosting | 5.00 | 77.3% (< 0.001) | 87.5% (< 0.001) | 33.7 |
| Point forecast + past errors of the same hour | 4.91 | 78.6% (< 0.001) | 88.3% (< 0.001) | 34.7 |
| 2025 only: QRA / past errors | 4.66 / 4.55 | 79.3% (0.10) / 79.8% (0.69) | 88.8% (< 0.001) / 89.2% (0.01) | 35.2 / 35.2 |

Pinball loss in EUR/MWh averaged over the 5%, 10%, ..., 95% quantiles (twice it approximates the CRPS). The second half of 2024 is the hardest period for both methods; the miss rates are tested with the Kupiec test of v0.2.

![Reliability](figures/forecast_reliability.png)

![Battery value of forecasts](figures/forecast_battery_value.png)

| 2-hour battery, thousand EUR per MW (share of perfect) | 2024 | 2025 |
|---|---|---|
| Perfect knowledge of the day's prices | 63.2 | 72.3 |
| Scheduled on LEAR + boosting forecast | 59.3 (94%) | 69.0 (95%) |
| Scheduled on LEAR | 58.6 (93%) | 68.2 (94%) |
| Scheduled on gradient boosting | 58.5 (93%) | 67.7 (94%) |
| Scheduled on the naive forecast | 52.1 (82%) | 61.6 (85%) |
| Scheduled on yesterday's prices | 48.3 (76%) | 58.2 (80%) |

**Method.** QRA (Nowotarski and Weron): for each of 19 quantile levels a linear quantile regression of the price on the LEAR and boosting point forecasts, fitted on the previous 182 days (pooled over hours) and recalibrated monthly; crossing quantiles are sorted. Benchmark: the LEAR + boosting point forecast plus the empirical quantiles of its errors in the same hour over the previous 182 days. Battery: the v0.3 model (1 MW, 2 MWh, 88% round trip, 10 EUR/MWh degradation) schedules each day on a forecast and is settled at actual prices.


![Example week](figures/forecast_example_week.png)

| Model | MAE 2024 | MAE 2025 | MAE 2024-2025 | rMAE vs naive | RMSE 2024-2025 |
|---|---|---|---|---|---|
| Naive (d-1, or d-7 on Monday and weekends) | 27.3 | 27.5 | 27.4 | 1.00 | 43.2 |
| LEAR, 364-day window | 13.1 | 12.9 | 13.0 | 0.48 | 23.9 |
| LEAR, 728-day window | 14.6 | 12.0 | 13.3 | 0.49 | 24.5 |
| LEAR, average of both windows | 13.4 | 12.1 | 12.8 | 0.47 | 23.7 |
| Gradient boosting | 14.2 | 12.7 | 13.4 | 0.49 | 24.1 |
| **LEAR + gradient boosting, average** | **12.4** | **11.5** | **12.0** | **0.44** | **22.6** |

EUR/MWh; out of sample (each forecast uses only data up to the day before). The better calibration window changes with the regime (one year in 2024, two years in 2025), which is why averaging windows is robust. Diebold-Mariano tests on the daily sum of absolute errors (`results/forecast/dm_pvalues.csv`): the LEAR + boosting average beats every other model (p < 0.001); the LEAR window average beats boosting (p = 0.005); the 364-day window beats the 728-day window over the two years (p = 0.04), while boosting is not significantly different from either single-window LEAR model.

![MAE by hour](figures/forecast_mae_by_hour.png)

![Monthly MAE](figures/forecast_monthly_mae.png)

**Method.** Data: day-ahead prices and the TSOs' day-ahead forecasts of load and of onshore wind, offshore wind and solar generation from SMARD (2021-2025), the last EEX EU-allowance auction price before the delivery day and the previous month's TTF gas price. Days are local with 24 hours (clock-change hours interpolated or averaged). LEAR: one LASSO per hour (penalty chosen by AIC) on 249 inputs: prices of d-1, d-2, d-3 and d-7, load and wind+solar forecasts for d, d-1 and d-7, weekday dummies, CO2 and gas; prices are standardised by median and MAD and transformed with asinh, which tames negative prices and spikes; recalibrated every 7 days on rolling windows of 364 and 728 days (the literature recalibrates daily; weekly keeps the run time at about 25 minutes). Gradient boosting: scikit-learn histogram gradient boosting on all hours with the same information plus summary features (yesterday's mean, minimum and maximum, residual-load forecast, renewable share), recalibrated monthly on 728 days. Note on timing: the TSOs publish their wind and solar day-ahead forecasts by 18:00 the day before, after the 12:00 auction; earlier forecasts exist but are not public, and the open benchmarks of the literature use the same series.


![Daily prices](figures/dispatch_daily_prices.png)

| Year | Sample | Actual mean | Model mean | MAE | RMSE | Correlation, hourly | Correlation, daily |
|---|---|---|---|---|---|---|---|
| 2023 | calibration | 95.2 | 92.9 | 20.9 | 32.3 | 0.74 | 0.85 |
| 2024 | out of sample | 78.5 | 77.4 | 20.3 | 37.3 | 0.71 | 0.82 |
| 2025 | out of sample | 89.3 | 83.7 | 22.6 | 36.2 | 0.73 | 0.83 |

Prices in EUR/MWh. Hours with prices above 200 EUR/MWh: 112, 129 and 162; hours with negative prices: 301, 457 and 573.

![Price duration](figures/dispatch_price_duration.png)

![Generation by fuel](figures/dispatch_generation.png)

| Thermal generation, TWh (model error) | 2023 | 2024 | 2025 |
|---|---|---|---|
| Lignite, actual | 77.8 (+12%) | 71.0 (+15%) | 67.2 (+12%) |
| Hard coal, actual | 39.8 (-2%) | 27.3 (-7%) | 28.2 (+5%) |
| Gas, actual | 51.2 (-15%) | 57.0 (-13%) | 60.6 (-12%) |

**Method.** Thermal demand per hour is load plus pumped-storage consumption minus wind, solar, hydro, biomass, other renewables, other conventional, nuclear and pumped-storage generation and net imports, all from SMARD; net imports (with any statistical difference between load and generation data, 21 to 45 TWh per year) close the balance, so thermal demand equals observed lignite, hard-coal and gas output and the model decides how it is split between fuels and at what marginal cost. Per fuel and month, available capacity is the maximum observed hourly output and must-run output a quantile of it; the capacity above must-run is cut into ten blocks whose efficiency falls linearly from the best to the worst plants (lignite 43 to 31%, hard coal 46 to 34%, gas 60 to 33%). Marginal cost = (fuel price + emission factor x CO2 price) / efficiency + variable O&M (emission factors 0.364, 0.338 and 0.202 tCO2/MWh thermal; O&M 4, 4 and 2 EUR/MWh). Each hour is dispatched in merit order and the price is the cost of the last block used, which equals the dual of the demand constraint of the hourly economic-dispatch LP (checked against SciPy/HiGHS in the tests); if must-run output alone covers demand the price is zero. Calibrated on 2023 by hourly price MAE over a grid: lignite fuel cost 4 EUR/MWh thermal and must-run at the 15th percentile of monthly output (`results/dispatch/calibration_2023.csv`).

**Fuel and carbon prices** (monthly, `results/dispatch/fuel_prices_monthly.csv`): natural gas Europe (TTF) and South African coal (6000 kcal/kg, the closest open series to the API2 benchmark) from the [World Bank Commodity Price Data](https://www.worldbank.org/en/research/commodity-markets) (CC BY 4.0), converted with the ECB monthly USD/EUR reference rate ([ECB Data Portal](https://data.ecb.europa.eu/)); EU allowances as monthly means of the [EEX primary auction](https://www.eex.com/en/markets/environmental-markets/eu-ets-auctions) clearing prices. Raw files are downloaded into `data/raw/fuels/` and not committed.

**Limitations.** No negative prices and no scarcity pricing: bids below or above marginal cost, start-up costs and minimum run times are not modelled, and the zero-price step stands in for hours that exports and flexibility actually price. Imports are taken as observed rather than priced, so the model explains the domestic margin only. Fuel prices are monthly averages (daily gas price swings are averaged out), the lignite fuel cost is an assumption calibrated on 2023, and capacities and must-run are inferred from observed output rather than from plant lists. The dispatch is per hour with no ramping or storage coupling.

## v0.3: battery day-ahead arbitrage

![Battery revenue](figures/storage_revenue.png)

| Profit, thousand EUR per MW (cycles per year) | 2023 | 2024 | 2025 |
|---|---|---|---|
| 1 hour | 28.6 (580) | 35.0 (596) | 39.9 (582) |
| 2 hours | 51.6 (549) | 63.3 (565) | 72.3 (549) |
| 4 hours | 79.1 (434) | 96.9 (434) | 113.5 (435) |
| 2 hours, no degradation cost | 63.5 (667) | 75.6 (680) | 84.3 (670) |
| 2 hours, 20 EUR/MWh degradation cost | 41.4 (468) | 52.9 (470) | 62.1 (468) |
| Naive schedule (yesterday's prices), share of optimum, 2 hours | 73% | 76% | 81% |
| Share of charged energy bought at negative prices, 2 hours | 7% | 13% | 16% |

![Charging profile](figures/storage_profile.png)

The battery cycles about 1.5 times per day: it charges at night (around 3:00) and at midday (12:00 to 14:00, the solar peak) and discharges in the morning (7:00 to 8:00) and evening (18:00 to 20:00) peaks.

![Spreads vs solar](figures/spreads_solar.png)

**Method.** For each local day a mixed-integer linear program (SciPy `milp`, HiGHS) chooses hourly charging and discharging (1 MW, 1, 2 or 4 MWh) to maximise revenue at that day's day-ahead prices minus a degradation cost per MWh discharged; a binary variable per hour rules out charging and discharging at the same time; the battery starts and ends each day half full. Day-ahead prices are known the day before delivery, so the schedule is achievable; the naive benchmark schedules on the previous day's prices and is settled at the actual ones. Outputs: `results/storage/` (daily results per duration, summary, degradation sensitivity, hourly profile, daily spreads, `summary.json`).

**Limitations.** Price-taker: the battery does not move prices, so the effect of a growing storage fleet on spreads (self-cannibalisation) is not modelled; historically spreads widened. Day-ahead only, no intraday, balancing or ancillary-service revenue, no grid fees or capex, so this is not a business case. The half-full constraint at midnight forces a recharge in the last hour of the day (visible at 23:00 in the profile). Hourly prices as published by SMARD, also after the switch to 15-minute day-ahead products on 1 October 2025.

## Method

- **Capture price** of a technology over a period: generation-weighted mean price, `sum(price * generation) / sum(generation)`. **Capture rate**: capture price divided by the baseload (time-weighted mean) price.
- **Curtailed capture price**: the same with negative-price hours excluded, as for a plant that stops producing when prices fall below zero.
- **Pay-as-produced PPA** at strike K: the offtaker takes every MWh at K and values it at the spot price, so its result per MWh is capture price minus K. The fair strike over a sample makes the generation-weighted result zero.
- **Baseload PPA**: the seller delivers a flat block at the baseload price and settles the difference between block and production at spot. With block volume equal to annual production, the seller's realised price is the baseload price minus the shape cost (baseload price minus capture price).
- **Cannibalisation**: ordinary least squares of the monthly solar capture rate on the monthly ratio of solar generation to load (36 months).
- Periods are calendar years and months in local time (Europe/Berlin); timestamps are stored in UTC.
- Capture prices are computed in SQL (DuckDB, `sql/capture_prices.sql`) and cross-checked in pandas in the tests.

## Data

Hourly series from [SMARD](https://www.smard.de/) (Bundesnetzagentur), licence CC BY 4.0, source: Bundesnetzagentur | SMARD.de:

| Series | SMARD filter | Unit |
|---|---|---|
| Day-ahead price, DE-LU | 4169 | EUR/MWh |
| Generation wind onshore | 4067 | MWh |
| Generation wind offshore | 1225 | MWh |
| Generation solar | 4068 | MWh |
| Grid load | 410 | MWh |

The raw weekly files are cached in `data/raw/` (not committed); the hourly table is stored in `data/market.duckdb`.

## Run

```bash
python -m venv .venv
.venv/Scripts/activate            # Windows; on Linux/macOS: source .venv/bin/activate
pip install -e ".[test]"
python -m deppa.run               # downloads 2023-2025 (cached), writes results/ and figures/
python -m deppa.validate          # v0.2: floor valuation checks and VaR/ES backtests, writes results/validation/
python -m deppa.storage_run       # v0.3: battery arbitrage 2023-2025 (about 8 minutes), writes results/storage/
python -m deppa.dispatch_run      # v0.4: merit-order price model, calibrated on 2023, writes results/dispatch/
python -m deppa.forecast_run      # v0.5: price forecasts 2024-2025 out of sample (about 25 minutes), writes results/forecast/
python -m deppa.probabilistic_run # v0.6: quantile forecasts and battery value of forecasts, writes results/probabilistic/
python -m deppa.econometrics_run  # v0.7: unit roots, cointegration, VAR, renewable forecast errors, writes results/econometrics/
python -m deppa.stochastic_run    # v0.8: battery under price uncertainty, EVPI, VSS, CVaR (parallel, ~10 minutes), writes results/stochastic/
pytest                            # offline tests on synthetic data
```

## Limitations

- Generation profiles are national fleet totals, not a single plant. A specific site has its own profile and therefore its own capture price.
- Volume risk is not assessed: national generation grows with installed capacity, so year-to-year volume changes in this data mix weather and new build. This needs capacity data (planned for a later version).
- From 1 October 2025 the day-ahead market clears in 15-minute periods; the hourly price series is used as published by SMARD.
- Historical analysis only: no forecast of future capture prices, and no imbalance costs, grid fees or guarantees of origin in the PPA values.

## Roadmap

- **v0.9**: price the margin better: an import supply curve from neighbouring zones, must-run bids below cost, daily gas prices and a unit-commitment variant (MILP with start-up costs and minimum load) for the low-price and scarcity hours.
- **v1.0**: scenarios (CO2 price, gas price shock, renewable share, coal exit) and capture prices and battery revenues under each scenario.
- Battery follow-ups: price-dependent bids and intraday recourse, a multi-day horizon, capex and payback.
- Validation follow-ups: volatility from EEX futures, seasonal filtered historical simulation for solar, stressed VaR.
