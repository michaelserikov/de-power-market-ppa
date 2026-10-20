# Model validation report: PPA floor valuation and PPA market-risk models

Version 0.2, data 2023-2025 (DE-LU day-ahead, SMARD). All numbers are produced by `python -m deppa.validate` and stored in `results/validation/`. Market inputs are illustrative (see Section 2); the report demonstrates validation methods, not a production sign-off.

## 1. Scope and models under validation

| Model | Purpose | Implementation |
|---|---|---|
| **V1. Black-76 floor model** | Value a 12-month floor at 60 EUR/MWh on the monthly average day-ahead price (a strip of monthly puts), as bought by a PPA seller to protect merchant revenue | `valuation.black76`, one constant volatility calibrated to month-on-month log changes of monthly average prices; each put expires at the end of its delivery month |
| **R1-R3. One-day VaR(99%) and ES(97.5%)** | Daily market risk of the offtaker of a pay-as-produced (PaP) PPA, solar and onshore wind, 100 GWh per year, strike equal to the 2023-2025 fair strike (53.65 and 73.53 EUR/MWh) | `risk.rolling_forecasts`, 365-day rolling window: R1 historical simulation (HS), R2 normal with EWMA volatility (lambda 0.94), R3 GARCH(1,1) with Student-t innovations, refitted every 20 days |

Validation tests: independent replication, analytic against numerical Greeks, benchmarking against a challenger model, sensitivity analysis, VaR backtests (Kupiec, Christoffersen, Basel traffic light) and an ES backtest. A remediation candidate (R4, HS by day type) was built and tested.

## 2. Data and inputs

- Hourly day-ahead prices and national wind and solar generation from SMARD (Bundesnetzagentur, CC BY 4.0), 26,304 hours, local calendar years 2023-2025, no gaps.
- **No forward or option market data.** The forward for every month of 2026 is set to the 2025 average baseload price (89.32 EUR/MWh) and the pricing date to 31 December 2025, discount rate 2%. Volatility is calibrated to spot data: 55.0% per year. A production validation would use EEX month futures and, where available, option-implied volatilities.
- The PPA plant is the national fleet profile scaled to 100 GWh per year, so new capacity does not change volumes. Daily P&L is the day's settlement result, sum over hours of volume times (price minus strike), not a mark-to-market of future deliveries.

## 3. Tests and results

### 3.1 Implementation: independent replication (V1)

- **Monte Carlo replication.** 30 prices (puts and calls, strikes 40-120, maturities 0.25, 0.5 and 1 year), each with 400,000 antithetic paths: the largest deviation from the formula is 1.64 standard errors, all within 3. The estimate converges at the expected 1/sqrt(n) rate (`figures/mc_convergence.png`).
- **Put-call parity** holds to 1.4e-14.
- **Greeks.** Analytic delta, gamma, vega and time sensitivity agree with central finite differences of the formula to a relative error of 3e-8. Delta and vega from bumped Monte Carlo with common random numbers agree within 0.2%.

Result: the Black-76 implementation is correct. No finding.

### 3.2 Benchmarking against a challenger model (V1)

The challenger is calibrated on daily prices and does not reuse the front-office volatility. Daily price = level + weekday effect + short-term deviation. The level is a driftless random walk (daily shock 1.91 EUR/MWh, 36.4 EUR/MWh per year) and the deviation an AR(1) with coefficient 0.50 (half-life 1.0 day, shock 23.0 EUR/MWh). Weekday effects range from +11.1 EUR/MWh (Wednesday) to -24.8 EUR/MWh (Sunday). The model is arithmetic, so negative prices are possible, and the option pays on the arithmetic average of the month. Its monthly average is normal, so it is priced in closed form and cross-checked by Monte Carlo (largest deviation 1.62 standard errors).

| Value of the 12-month floor, sum of monthly puts (EUR/MWh-month) | |
|---|---|
| Black-76, expiry at month end (model under validation) | 30.19 |
| Black-76, variance time of a monthly average (remediation) | 26.66 (-11.7%) |
| Challenger, two-factor | 22.81 (Black-76 is 32% higher) |
| Challenger with its AR(1) coefficient corrected for estimation bias (+0.07) | 6.08 (-73% vs challenger) |

- **Averaging.** The floor settles on the monthly average, but the model lets the full volatility act until month end. Over a month, a random walk averaged daily has the variance of a point observed about two thirds of the month earlier. Using that variance time within Black-76 lowers the floor value by 11.7%. This is a structural error, independent of the challenger (Figure `figures/floor_strip.png`).
- **Volatility level.** The challenger implies Black-76 volatilities of 48-50%, against 55% in the model. But its own split of monthly variance between level and short-term noise is poorly identified: on synthetic data the AR(1) estimate is biased down by about 0.07 (tests), and correcting for that moves most of the variance into short-term noise and cuts the challenger value by 73%. The challenger therefore confirms the direction (the model overvalues the floor) but cannot fix the size of the gap from three years of spot data.

### 3.3 Sensitivity (V1)

Six-month put at 60 EUR/MWh, base value 2.23 EUR/MWh: a volatility shift of -10 or +10 points gives 1.16 or 3.51 (-48% or +57%); a forward shift of +10% or -10% gives 1.43 or 3.46. The value is dominated by the volatility input, which is the least reliable input (3.2).

### 3.4 Backtesting VaR and ES (R1-R4)

731 one-day forecasts (2024-2025), 7.3 exceptions expected at 99%. Tests at the 5% level; zones from the cumulative binomial probability (for 250 days: green 0-4, yellow 5-9, red 10 or more).

| Position | Model | Exceptions (on weekends/holidays) | Kupiec p | Independence p | Zone, full / worst 250 days | ES test p | Mean VaR (kEUR) |
|---|---|---|---|---|---|---|---|
| Solar | R1 HS | 10 (10) | 0.34 | 0.60 | green / yellow (5) | 0.92 | 40.4 |
| Solar | R2 EWMA normal | 21 (20) | <0.001 | <0.001 | red / red (13) | 0.002 | 27.0 |
| Solar | R3 GARCH-t | 19 (17) | <0.001 | 0.51 | red / red (13) | 0.22 | 24.8 |
| Solar | R4 HS by day type | 14 (3) | 0.03 | <0.001 | yellow / yellow (9) | 0.79 | 30.9 |
| Wind onshore | R1 HS | 10 (8) | 0.34 | <0.001 | green / yellow (6) | 0.18 | 45.0 |
| Wind onshore | R2 EWMA normal | 30 (19) | <0.001 | 0.04 | red / red (17) | <0.001 | 25.7 |
| Wind onshore | R3 GARCH-t | 24 (15) | <0.001 | 0.20 | red / red (11) | 0.04 | 24.4 |
| Wind onshore | R4 HS by day type | 11 (5) | 0.20 | 0.15 | green / yellow (6) | 0.09 | 39.9 |

ES test: on days the loss exceeds VaR(97.5%), the mean of loss minus ES should be zero; one-sided bootstrap p-value against ES being too low (McNeil-Frey type).

- **Parametric models fail.** EWMA and GARCH-t produce 2.6 to 4.1 times the expected number of exceptions and fall in the red zone for both positions. Of the solar exceptions, 20 of 21 (EWMA) and 17 of 19 (GARCH) fall on weekends or public holidays, mostly March to September. The largest losses come from calendar-driven negative-price days (worst day 2 July 2023, -102.8 kEUR, prices down to -500 EUR/MWh), which a volatility model does not anticipate from the previous days.
- **HS passes coverage but not everything.** HS has the right number of exceptions over the full sample, but reaches the yellow zone in its worst 250 days, its wind exceptions cluster (independence rejected) and its VaR barely moves with the seasons. The higher mean VaR (40-45 kEUR against about 25 kEUR) partly reflects a conservative level in quiet months.
- **Remediation R4.** HS restricted to past days of the same type (working day vs weekend or holiday) passes all tests for wind (11 exceptions, Kupiec 0.20, independence 0.15, conditional coverage 0.16, ES 0.09). For solar it moves the exceptions to working days and fails: solar volume seasonality is still mixed in the 365-day window.

## 4. Findings

| ID | Severity | Finding |
|---|---|---|
| F1 | High | V1 ignores the averaging of the underlying and overstates the floor value by 11.7% under its own assumptions. |
| F2 | High | V1's volatility is calibrated to spot monthly averages, which mix predictable seasonal shape and short-term noise with forward risk. The value is highly sensitive to it (vega: -48% / +57% for -/+10 points) and the challenger cannot pin it down from spot data. |
| F3 | High | R2 and R3 do not meet backtesting standards for either position (red zone, coverage rejected). Exceptions concentrate on weekends and holidays. |
| F4 | Medium | R1 meets coverage over the full sample but is yellow in its worst year, shows clustered exceptions for wind and does not adapt to seasonal risk. |
| F5 | Low | V1 is lognormal and excludes negative prices. Monthly averages stayed positive in 2023-2025 (minimum 61.3 EUR/MWh, February 2024), so the impact on monthly floors is small, but it would matter for daily or hourly settled products. |
| F6 | Low (challenger) | The challenger's AR(1) estimate is biased by the detrending step and its level/noise split is not identified. It is suitable as a directional benchmark, not as a pricing model. |

## 5. Recommendations

1. **F1:** replace month-end expiry with the variance time of the monthly average (moment matching, as in Turnbull-Wakeman type approximations); implemented here as `black76_avg_time`.
2. **F2:** calibrate volatility to EEX month futures (historical) or option-implied volatilities, with a term structure by delivery month. Until then, hold a model reserve sized from the sensitivity range.
3. **F3:** do not use R2 or R3 for limits or capital for these positions. If a parametric model is required, add calendar regressors (day type, season) to the mean and variance.
4. **F4 and remediation:** for wind, adopt HS by day type (R4) and monitor. For solar, condition on both day type and season, or scale historical P&L by the seasonal volume profile (filtered HS), and re-run the backtests.
5. Add a stressed VaR based on the July 2023 negative-price event and the December 2024 scarcity prices (936 EUR/MWh).

## 6. Limitations of this validation

Illustrative forwards and volatility (no market data); national fleet profiles instead of a specific plant; daily settlement P&L instead of mark-to-market; three years of data, one window length (365 days) and a single strike; nationwide public holidays only; no counterparty, volume or basis risk. From 1 October 2025 the day-ahead market clears in 15-minute periods; the hourly series is used as published by SMARD.
