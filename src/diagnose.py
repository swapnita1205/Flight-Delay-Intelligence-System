"""
Quick diagnostic: shows per-filter row counts for `flights_raw` so we can
see which WHERE clause is dropping rows in the cleaning step.

Usage:
    python src/diagnose.py
"""

from sqlalchemy import text

from database import get_engine


CHECKS = [
    ("total rows                ", "SELECT COUNT(*) FROM flights_raw"),
    ("diverted = 0              ", "SELECT COUNT(*) FROM flights_raw WHERE COALESCE(diverted, 0) = 0"),
    ("distance > 0              ", "SELECT COUNT(*) FROM flights_raw WHERE distance > 0"),
    ("month between 1 and 12    ", "SELECT COUNT(*) FROM flights_raw WHERE month BETWEEN 1 AND 12"),
    ("day_of_week between 1-7   ", "SELECT COUNT(*) FROM flights_raw WHERE day_of_week BETWEEN 1 AND 7"),
    ("fl_date IS NOT NULL       ", "SELECT COUNT(*) FROM flights_raw WHERE fl_date IS NOT NULL"),
    ("op_unique_carrier NOT NULL", "SELECT COUNT(*) FROM flights_raw WHERE op_unique_carrier IS NOT NULL"),
    ("origin IS NOT NULL        ", "SELECT COUNT(*) FROM flights_raw WHERE origin IS NOT NULL"),
    ("dest IS NOT NULL          ", "SELECT COUNT(*) FROM flights_raw WHERE dest IS NOT NULL"),
]


def main() -> None:
    engine = get_engine()
    with engine.connect() as conn:
        print("\n=== filter pass-through counts ===")
        for label, sql in CHECKS:
            count = conn.execute(text(sql)).scalar()
            print(f"  {label} : {count:,}")

        print("\n=== sample rows ===")
        sample = conn.execute(text("""
            SELECT fl_date, op_unique_carrier, origin, dest,
                   month, day_of_week, distance, cancelled, diverted
            FROM flights_raw
            LIMIT 3
        """)).fetchall()
        if not sample:
            print("  (no rows)")
        for row in sample:
            print(" ", dict(row._mapping))

        print("\n=== column names actually present ===")
        cols = conn.execute(text("""
            SELECT column_name
            FROM information_schema.columns
            WHERE table_name = 'flights_raw'
            ORDER BY ordinal_position
        """)).fetchall()
        print(" ", [r[0] for r in cols])


if __name__ == "__main__":
    main()
