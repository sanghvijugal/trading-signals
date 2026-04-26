"""
Database migration — adds new columns and tables introduced in v2.

Run once after deploying the new schema:
    python migrate.py

Safe to run multiple times — uses IF NOT EXISTS / IF NOT COLUMN EXISTS patterns.
"""
from sqlalchemy import text
from storage.db import engine, init_db


MIGRATIONS = [
    # v2 columns
    "ALTER TABLE signals ADD COLUMN IF NOT EXISTS polymarket_divergence_score FLOAT",
    "ALTER TABLE signals ADD COLUMN IF NOT EXISTS price_divergence_score FLOAT",
    "ALTER TABLE signals ADD COLUMN IF NOT EXISTS vix_score FLOAT",
    "ALTER TABLE signals ADD COLUMN IF NOT EXISTS macro_context_score FLOAT",
    # v3 columns
    "ALTER TABLE signals ADD COLUMN IF NOT EXISTS trigger_source VARCHAR(32)",
]


def run():
    print("[Migrate] Running migrations...")

    with engine.begin() as conn:
        for sql in MIGRATIONS:
            try:
                conn.execute(text(sql))
                print(f"[Migrate] OK: {sql[:60]}")
            except Exception as e:
                print(f"[Migrate] Skipped ({e}): {sql[:60]}")

    # Create any brand-new tables (polymarket_snapshots, macro_snapshots)
    init_db()
    print("[Migrate] New tables created (if not exist)")
    print("[Migrate] Done.")


if __name__ == "__main__":
    run()
