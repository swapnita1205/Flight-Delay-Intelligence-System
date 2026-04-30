"""
Run any .sql file against PostgreSQL using credentials from .env.

This is a thin wrapper so we don't have to fight with psql env vars
or set DATABASE_URL in the shell. It uses the same SQLAlchemy engine
as the rest of the pipeline.

Usage:
    python src/run_sql.py sql/01_create_tables.sql
    python src/run_sql.py sql/02_cleaning_views.sql
    python src/run_sql.py sql/03_feature_tables.sql
"""

from __future__ import annotations

import logging
import sys
from pathlib import Path

from sqlalchemy import text

from database import get_engine


logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(message)s",
)
log = logging.getLogger("run_sql")


def run_sql_file(path: Path) -> None:
    """Execute a .sql file statement-by-statement and print any results."""
    sql = path.read_text()
    engine = get_engine()

    with engine.begin() as conn:
        for statement in sql.split(";"):
            stmt = statement.strip()
            if not stmt:
                continue
            result = conn.execute(text(stmt))
            if result.returns_rows:
                rows = result.fetchall()
                cols = list(result.keys())
                preview = rows[:5]
                log.info("Result %s: %s%s", cols, preview,
                         " ..." if len(rows) > len(preview) else "")


def main() -> None:
    if len(sys.argv) != 2:
        print("Usage: python src/run_sql.py <path-to-sql-file>")
        sys.exit(1)

    path = Path(sys.argv[1])
    if not path.exists():
        log.error("File not found: %s", path)
        sys.exit(1)

    log.info("Running %s", path)
    run_sql_file(path)
    log.info("Done.")


if __name__ == "__main__":
    main()
