"""
Ingest BTS On-Time Performance CSV files into PostgreSQL.

Steps:
    1. Find every CSV file in data/raw/.
    2. Standardize column names to lowercase snake_case.
    3. Keep only the columns we use downstream.
    4. Append the cleaned dataframe to the `flights_raw` table.

Usage:
    python src/ingest.py
"""

from __future__ import annotations

import io
import logging
import sys
import time
from pathlib import Path

import pandas as pd
from tqdm import tqdm

from config import RAW_DIR
from database import get_engine


REQUIRED_COLUMNS = [
    "year",
    "month",
    "day_of_month",
    "day_of_week",
    "fl_date",
    "op_unique_carrier",
    "origin",
    "dest",
    "crs_dep_time",
    "dep_time",
    "dep_delay",
    "crs_arr_time",
    "arr_time",
    "arr_delay",
    "cancelled",
    "cancellation_code",
    "diverted",
    "air_time",
    "distance",
    "carrier_delay",
    "weather_delay",
    "nas_delay",
    "security_delay",
    "late_aircraft_delay",
]

# Columns declared as INTEGER in the schema. Pandas turns these into
# float64 whenever they contain NaN, which then fails Postgres COPY
# ("invalid input syntax for type integer: '452.0'"). Casting to the
# nullable Int64 dtype keeps NaNs as <NA> and writes clean integers.
INT_COLUMNS = [
    "year",
    "month",
    "day_of_month",
    "day_of_week",
    "crs_dep_time",
    "dep_time",
    "crs_arr_time",
    "arr_time",
]

TARGET_TABLE = "flights_raw"
READ_CHUNK_SIZE = 50_000

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(message)s",
)
log = logging.getLogger("ingest")


COLUMN_ALIASES = {
    "reporting_airline": "op_unique_carrier",
}


def standardize_columns(df: pd.DataFrame) -> pd.DataFrame:
    """Lowercase, snake_case, and remap BTS aliases to our canonical names."""
    df.columns = (
        df.columns.str.strip()
        .str.lower()
        .str.replace(r"\s+", "_", regex=True)
    )
    df = df.rename(columns=COLUMN_ALIASES)
    return df


def select_required_columns(df: pd.DataFrame, file_name: str) -> pd.DataFrame:
    """Keep only the columns we care about, warn about missing ones."""
    available = [c for c in REQUIRED_COLUMNS if c in df.columns]
    missing = [c for c in REQUIRED_COLUMNS if c not in df.columns]

    if missing:
        log.warning("%s missing columns: %s", file_name, missing)

    return df[available].copy()


def prepare_chunk(chunk: pd.DataFrame, file_name: str) -> pd.DataFrame:
    """Apply column standardization, date parsing, and integer casting."""
    chunk = standardize_columns(chunk)
    chunk = select_required_columns(chunk, file_name)

    if "fl_date" in chunk.columns:
        # BTS sometimes ships fl_date as "2025-02-01" and sometimes as
        # "2/1/2025 12:00:00 AM". format="mixed" handles both without
        # the slow per-row dateutil fallback.
        chunk["fl_date"] = pd.to_datetime(
            chunk["fl_date"], format="mixed", errors="coerce"
        ).dt.date

    for col in INT_COLUMNS:
        if col in chunk.columns:
            chunk[col] = chunk[col].astype("Int64")

    return chunk


def copy_dataframe(df: pd.DataFrame, table: str, engine) -> None:
    """
    Bulk-load a DataFrame into Postgres using the native COPY command.

    This is roughly 20-30x faster than `df.to_sql(method="multi")` because
    COPY streams the rows in a single operation instead of building giant
    multi-row INSERT statements.
    """
    buffer = io.StringIO()
    df.to_csv(buffer, index=False, header=False, na_rep="")
    buffer.seek(0)

    columns = ", ".join(df.columns)
    copy_sql = (
        f"COPY {table} ({columns}) "
        f"FROM STDIN WITH (FORMAT CSV, NULL '')"
    )

    raw_conn = engine.raw_connection()
    try:
        with raw_conn.cursor() as cur:
            cur.copy_expert(copy_sql, buffer)
        raw_conn.commit()
    except Exception:
        raw_conn.rollback()
        raise
    finally:
        raw_conn.close()


def count_rows(path: Path) -> int:
    """
    Fast line count for the file (minus the header).
    Used to give the progress bar a known total.
    """
    with open(path, "rb") as f:
        return sum(1 for _ in f) - 1


def ingest_file(path: Path, engine) -> int:
    """
    Stream a single CSV into flights_raw in chunks, with a tqdm progress
    bar showing rows processed. Returns total rows inserted.
    """
    total = count_rows(path)
    if total <= 0:
        log.warning("%s is empty, skipping", path.name)
        return 0

    inserted = 0
    start = time.perf_counter()
    pbar = tqdm(
        total=total,
        unit="rows",
        unit_scale=True,
        desc=path.name,
        ncols=100,
    )

    chunk_iter = pd.read_csv(path, chunksize=READ_CHUNK_SIZE, low_memory=False)
    for chunk in chunk_iter:
        chunk = prepare_chunk(chunk, path.name)
        if not chunk.empty:
            copy_dataframe(chunk, TARGET_TABLE, engine)
            inserted += len(chunk)
        pbar.update(len(chunk))

    pbar.close()
    elapsed = time.perf_counter() - start
    log.info(
        "Inserted %s rows from %s in %.1fs (%.0f rows/s)",
        inserted, path.name, elapsed, inserted / max(elapsed, 1e-6),
    )
    return inserted


def main() -> None:
    csv_files = sorted(RAW_DIR.glob("*.csv"))
    if not csv_files:
        log.error("No CSV files found in %s", RAW_DIR)
        sys.exit(1)

    log.info("Found %s CSV file(s) to ingest", len(csv_files))
    engine = get_engine()

    total = 0
    file_iter = (
        tqdm(csv_files, desc="Files", unit="file", position=1)
        if len(csv_files) > 1
        else csv_files
    )
    for path in file_iter:
        total += ingest_file(path, engine)

    log.info("Done. Inserted %s total rows into flights_raw.", total)


if __name__ == "__main__":
    main()
