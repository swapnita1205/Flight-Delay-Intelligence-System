"""
Database connection helpers for PostgreSQL.

Use `get_engine()` to obtain a SQLAlchemy engine that other modules
(ingest, features, save_predictions) can share.
"""

from sqlalchemy import create_engine
from sqlalchemy.engine import Engine

from config import database_url


def get_engine() -> Engine:
    """Create a SQLAlchemy engine using credentials from .env."""
    return create_engine(database_url(), pool_pre_ping=True)


def test_connection() -> bool:
    """Quick sanity check that the database is reachable."""
    engine = get_engine()
    try:
        with engine.connect() as conn:
            conn.exec_driver_sql("SELECT 1;")
        return True
    except Exception as exc:
        print(f"Database connection failed: {exc}")
        return False


if __name__ == "__main__":
    print("Testing database connection...")
    print("OK" if test_connection() else "FAILED")
