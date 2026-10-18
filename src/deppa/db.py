"""Hourly market table in DuckDB and the SQL queries on it."""

from __future__ import annotations

from pathlib import Path

import duckdb
import pandas as pd

SQL_DIR = Path(__file__).resolve().parents[2] / "sql"
TZ = "Europe/Berlin"


def prepare_hourly(raw: pd.DataFrame) -> pd.DataFrame:
    """Add local (Berlin) calendar columns; periods are local years and months."""
    df = raw.copy()
    local = df["ts_utc"].dt.tz_convert(TZ)
    df["year"] = local.dt.year.astype("int32")
    df["month"] = local.dt.month.astype("int32")
    df["hour_local"] = local.dt.hour.astype("int32")
    return df


def connect(hourly: pd.DataFrame, path: str | Path = ":memory:") -> duckdb.DuckDBPyConnection:
    """A DuckDB connection holding table `hourly` (replaced if it exists)."""
    con = duckdb.connect(str(path))
    con.register("hourly_df", hourly)
    con.execute("CREATE OR REPLACE TABLE hourly AS SELECT * FROM hourly_df")
    con.unregister("hourly_df")
    return con


def capture_prices(con: duckdb.DuckDBPyConnection, period: str = "year") -> pd.DataFrame:
    """Capture prices per technology; period is 'year' or 'year, month'."""
    if period not in ("year", "year, month"):
        raise ValueError("period must be 'year' or 'year, month'")
    sql = (SQL_DIR / "capture_prices.sql").read_text(encoding="utf-8").replace("{period}", period)
    return con.execute(sql).df()
