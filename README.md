# German power market: capture prices and PPA valuation (v0.1)

What is a MWh of wind or solar power actually worth on the German day-ahead market, and what does that mean for a power purchase agreement (PPA)? This project answers that from hourly market data for 2023 to 2025 (bidding zone DE-LU, 26,304 hours, no gaps): capture prices and capture rates, the cost of negative prices, the fair strike of a pay-as-produced PPA, the shape cost of a baseload PPA and the month-to-month risk an offtaker carries.

**Main findings**
- Solar cannibalises its own price. The solar capture rate fell from 76% (2023) to 59% (2024) and 52% (2025), while wind onshore stayed at 82-87% and wind offshore at 91-96%. Across months, each additional percentage point of solar in the load lowers the solar capture rate by about 2.1 points.
- The fair pay-as-produced strike for solar dropped from 72 EUR/MWh (2023) to 46 EUR/MWh (2024 and 2025). A solar PPA priced on 2023 data would have overpaid by about 26 EUR/MWh in the following two years.
- Negative prices matter mostly for solar: 24% of 2025 solar output fell into negative-price hours. A plant that stops producing in those hours would have raised its 2025 capture price from 46 to 65 EUR/MWh.
- Selling solar as a baseload product carries a growing shape cost: 23 EUR/MWh in 2023, 32 in 2024 and 43 in 2025 (24%, 41% and 48% of the baseload price).

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
pytest                            # offline tests on synthetic data
```

## Limitations

- Generation profiles are national fleet totals, not a single plant. A specific site has its own profile and therefore its own capture price.
- Volume risk is not assessed: national generation grows with installed capacity, so year-to-year volume changes in this data mix weather and new build. This needs capacity data (planned for v0.2).
- From 1 October 2025 the day-ahead market clears in 15-minute periods; the hourly price series is used as published by SMARD.
- Historical analysis only: no forecast of future capture prices, and no imbalance costs, grid fees or guarantees of origin in the PPA values.

## Roadmap

- **v0.2**: a merit-order dispatch model of the German market (linear program) that reproduces hourly prices, validated against the actual day-ahead prices.
- **v0.3**: scenarios (CO2 price, gas price shock, renewable share, coal exit) and capture prices under each scenario.
