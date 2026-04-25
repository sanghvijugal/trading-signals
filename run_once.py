"""
Single-pass pipeline run — used by GitHub Actions.
No scheduler needed; the cron in collect.yml handles the interval.
"""
from storage.db import init_db
from pipeline.collector import run_pipeline

if __name__ == "__main__":
    init_db()
    run_pipeline()
