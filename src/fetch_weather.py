"""
Fetch hourly weather observations from the NOAA Climate Data Online (CDO) API
and load them into the `airport_weather` PostgreSQL table.

Data source  : NOAA Local Climatological Data (LCD), dataset ID "LCD"
Resolution   : hourly observations per airport IATA code
Key fields   : HourlyPrecipitation, HourlyVisibility, HourlyWindSpeed

Prerequisites
-------------
1. Register for a free CDO token at https://www.ncdc.noaa.gov/cdo-web/token
2. Set NOAA_CDO_TOKEN in your .env (or environment).

Usage
-----
    python src/fetch_weather.py --start-date 2022-01-01 --end-date 2022-12-31

The script skips airport-months already present in airport_weather, so it
is safe to re-run incrementally.

Rate limits
-----------
The free CDO tier allows 1,000 requests/day and 1,000 results/request.
The script paginates automatically and sleeps between pages to stay within
limits.  For multi-year backfills, run it month-by-month or spread across days.
"""

from __future__ import annotations

import argparse
import logging
import os
import time
from datetime import date, timedelta
from typing import Iterator

import numpy as np
import pandas as pd
import requests
from dateutil.relativedelta import relativedelta
from sqlalchemy import text

from config import PROJECT_ROOT
from database import get_engine

try:
    from dotenv import load_dotenv
    load_dotenv(PROJECT_ROOT / ".env")
except ImportError:
    pass

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(message)s",
)
log = logging.getLogger("fetch_weather")

CDO_BASE = "https://www.ncei.noaa.gov/cdo-web/api/v2/data"
PAGE_LIMIT = 1000
REQUEST_DELAY = 0.25  # seconds between CDO API calls

# IATA code → NOAA CDO station ID (WBAN-based LCD stations for major US airports).
AIRPORT_STATION: dict[str, str] = {
    "ATL": "WBAN:13874",
    "ORD": "WBAN:94846",
    "DFW": "WBAN:03927",
    "DEN": "WBAN:03017",
    "LAX": "WBAN:23174",
    "JFK": "WBAN:94789",
    "LGA": "WBAN:14732",
    "EWR": "WBAN:14734",
    "SFO": "WBAN:23234",
    "SEA": "WBAN:24233",
    "MIA": "WBAN:12839",
    "MCO": "WBAN:12815",
    "PHX": "WBAN:23183",
    "LAS": "WBAN:23169",
    "BOS": "WBAN:14739",
    "MSP": "WBAN:14922",
    "DTW": "WBAN:94847",
    "CLT": "WBAN:13881",
    "IAH": "WBAN:12960",
    "MDW": "WBAN:14819",
    "SLC": "WBAN:24127",
    "PDX": "WBAN:24229",
    "BWI": "WBAN:93721",
    "IAD": "WBAN:93738",
    "DCA": "WBAN:13743",
}

DATA_TYPES = ["HourlyPrecipitation", "HourlyVisibility", "HourlyWindSpeed"]


def month_ranges(start: date, end: date) -> Iterator[tuple[date, date]]:
    """Yield (first_day, last_day) pairs for each calendar month in [start, end]."""
    cur = start.replace(day=1)
    while cur <= end:
        last = (cur + relativedelta(months=1)) - timedelta(days=1)
        yield cur, min(last, end)
        cur += relativedelta(months=1)


def fetch_lcd_month(
    token: str,
    station_id: str,
    start: date,
    end: date,
) -> list[dict]:
    """Fetch all LCD hourly records for one station over one calendar month."""
    records: list[dict] = []
    offset = 1

    while True:
        params = {
            "datasetid": "LCD",
            "stationid": station_id,
            "startdate": start.isoformat(),
            "enddate": end.isoformat(),
            "datatypeid": ",".join(DATA_TYPES),
            "units": "standard",
            "limit": PAGE_LIMIT,
            "offset": offset,
        }
        try:
            resp = requests.get(
                CDO_BASE,
                headers={"token": token},
                params=params,
                timeout=30,
            )
            resp.raise_for_status()
        except requests.RequestException as exc:
            log.warning("CDO request failed (%s) — skipping page offset=%d", exc, offset)
            break

        payload = resp.json()
        results = payload.get("results", [])
        records.extend(results)

        total = payload.get("metadata", {}).get("resultset", {}).get("count", len(results))
        if offset + PAGE_LIMIT > total:
            break
        offset += PAGE_LIMIT
        time.sleep(REQUEST_DELAY)

    return records


def parse_lcd_records(airport_code: str, raw: list[dict]) -> pd.DataFrame:
    """Parse CDO LCD response into one tidy row per (airport, date, hour)."""
    if not raw:
        return pd.DataFrame()

    rows: dict[tuple, dict] = {}
    for rec in raw:
        dt_str = rec.get("date", "")
        if not dt_str:
            continue
        try:
            dt = pd.to_datetime(dt_str)
        except Exception:
            continue

        key = (airport_code, dt.date(), dt.hour)
        if key not in rows:
            rows[key] = {
                "airport_code": airport_code,
                "obs_date": dt.date(),
                "obs_hour": dt.hour,
            }

        dtype = rec.get("datatype", "")
        raw_val = rec.get("value", "")
        try:
            # "T" means trace precipitation (<0.005 in) — treat as 0
            val = float(raw_val) if raw_val not in ("", "T", None) else 0.0
        except (ValueError, TypeError):
            val = np.nan

        if dtype == "HourlyPrecipitation":
            rows[key]["precip_in"] = val
        elif dtype == "HourlyVisibility":
            rows[key]["visibility_mi"] = val
        elif dtype == "HourlyWindSpeed":
            rows[key]["wind_speed_mph"] = val

    df = pd.DataFrame(rows.values())
    for col in ("precip_in", "visibility_mi", "wind_speed_mph"):
        if col not in df.columns:
            df[col] = np.nan
    return df


def already_fetched(engine, airport_code: str, month_start: date) -> bool:
    """Return True if airport_weather already has rows for this airport-month."""
    month_end = (month_start + relativedelta(months=1)) - timedelta(days=1)
    sql = text(
        "SELECT 1 FROM airport_weather "
        "WHERE airport_code = :code AND obs_date BETWEEN :s AND :e LIMIT 1"
    )
    with engine.connect() as conn:
        result = conn.execute(sql, {"code": airport_code, "s": month_start, "e": month_end})
        return result.fetchone() is not None


def upsert_weather(engine, df: pd.DataFrame) -> None:
    """Append weather rows; duplicates are silently skipped via ON CONFLICT DO NOTHING."""
    if df.empty:
        return
    # Use raw connection for COPY-style insert with conflict handling
    with engine.begin() as conn:
        for _, row in df.iterrows():
            conn.execute(
                text(
                    "INSERT INTO airport_weather "
                    "(airport_code, obs_date, obs_hour, precip_in, visibility_mi, wind_speed_mph) "
                    "VALUES (:code, :d, :h, :p, :v, :w) "
                    "ON CONFLICT (airport_code, obs_date, obs_hour) DO NOTHING"
                ),
                {
                    "code": row["airport_code"],
                    "d": row["obs_date"],
                    "h": int(row["obs_hour"]),
                    "p": None if pd.isna(row.get("precip_in", np.nan)) else float(row["precip_in"]),
                    "v": None if pd.isna(row.get("visibility_mi", np.nan)) else float(row["visibility_mi"]),
                    "w": None if pd.isna(row.get("wind_speed_mph", np.nan)) else float(row["wind_speed_mph"]),
                },
            )


def main(start_date: date, end_date: date, airports: list[str] | None = None) -> None:
    token = os.getenv("NOAA_CDO_TOKEN", "")
    if not token:
        log.error(
            "NOAA_CDO_TOKEN not set. Register for a free token at "
            "https://www.ncdc.noaa.gov/cdo-web/token and add it to .env"
        )
        return

    engine = get_engine()
    targets = airports if airports else list(AIRPORT_STATION.keys())
    log.info("Fetching weather for %d airports from %s to %s", len(targets), start_date, end_date)

    for airport in targets:
        station_id = AIRPORT_STATION.get(airport)
        if not station_id:
            log.warning("No CDO station mapping for %s — skipping", airport)
            continue

        for month_start, month_end in month_ranges(start_date, end_date):
            if already_fetched(engine, airport, month_start):
                log.info(
                    "%s %s — already present in airport_weather, skipping",
                    airport,
                    month_start.strftime("%Y-%m"),
                )
                continue

            log.info("Fetching %s  %s → %s", airport, month_start, month_end)
            raw = fetch_lcd_month(token, station_id, month_start, month_end)
            df = parse_lcd_records(airport, raw)

            if df.empty:
                log.warning("No records returned for %s %s", airport, month_start.strftime("%Y-%m"))
                continue

            upsert_weather(engine, df)
            log.info(
                "Inserted %d rows for %s %s",
                len(df),
                airport,
                month_start.strftime("%Y-%m"),
            )
            time.sleep(REQUEST_DELAY)

    log.info("Weather fetch complete.")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Fetch NOAA hourly weather data into the airport_weather table"
    )
    parser.add_argument("--start-date", required=True, help="YYYY-MM-DD")
    parser.add_argument("--end-date", required=True, help="YYYY-MM-DD")
    parser.add_argument(
        "--airports",
        nargs="*",
        help="Space-separated IATA codes to fetch (default: all mapped airports)",
    )
    args = parser.parse_args()

    main(
        start_date=date.fromisoformat(args.start_date),
        end_date=date.fromisoformat(args.end_date),
        airports=args.airports,
    )
