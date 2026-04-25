"""
Entry point. Runs the collection pipeline every 5 minutes.
Also runs once immediately on startup.

Usage:
    python main.py
"""
from apscheduler.schedulers.blocking import BlockingScheduler
from storage.db import init_db
from pipeline.collector import run_pipeline


def main():
    init_db()
    print("[System] Database initialized")
    print("[System] Starting scheduler — collecting every 5 minutes")
    print("[System] Press Ctrl+C to stop\n")

    scheduler = BlockingScheduler(timezone="UTC")
    scheduler.add_job(run_pipeline, "interval", minutes=5, id="pipeline")

    # Run immediately on startup before scheduler takes over
    run_pipeline()

    try:
        scheduler.start()
    except KeyboardInterrupt:
        print("\n[System] Stopped by user")


if __name__ == "__main__":
    main()
