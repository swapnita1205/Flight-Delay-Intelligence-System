"""
Wrapper that runs the SQL cleaning script (sql/02_cleaning_views.sql)
against PostgreSQL.

Most of the cleaning logic lives in SQL for performance. This script just
makes it easy to trigger from the command line:

    python src/clean.py
"""

import logging

from sqlalchemy import text

from config import SQL_DIR
from database import get_engine


logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(message)s",
)
log = logging.getLogger("clean")


def run_sql_file(path) -> None:
    """Execute a .sql file statement-by-statement."""
    sql = path.read_text()
    engine = get_engine()

    with engine.begin() as conn:
        for statement in sql.split(";"):
            stmt = statement.strip()
            if stmt:
                conn.execute(text(stmt))


def main() -> None:
    cleaning_sql = SQL_DIR / "02_cleaning_views.sql"
    log.info("Running %s", cleaning_sql.name)
    run_sql_file(cleaning_sql)
    log.info("Cleaning complete.")


if __name__ == "__main__":
    main()
