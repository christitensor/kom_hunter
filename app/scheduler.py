import logging
from datetime import datetime, timedelta

from apscheduler.schedulers.background import BackgroundScheduler

from app import checker
from app.config import CHECK_INTERVAL_HOURS
from app.db import SessionLocal

logger = logging.getLogger("kom_hunter.scheduler")

_scheduler: BackgroundScheduler | None = None


def _run_check_job() -> None:
    db = SessionLocal()
    try:
        results = checker.check_all_segments(db)
        total_alerts = sum(len(w) for w in results.values())
        logger.info("Scheduled check complete: %d segment(s), %d new alert(s)", len(results), total_alerts)
    finally:
        db.close()


def start_scheduler() -> BackgroundScheduler:
    global _scheduler
    if _scheduler is not None:
        return _scheduler

    _scheduler = BackgroundScheduler(timezone="UTC")
    _scheduler.add_job(
        _run_check_job,
        "interval",
        hours=CHECK_INTERVAL_HOURS,
        id="check_all_segments",
        # Run once shortly after startup, then on the regular interval.
        next_run_time=datetime.utcnow() + timedelta(seconds=15),
    )
    _scheduler.start()
    return _scheduler


def stop_scheduler() -> None:
    global _scheduler
    if _scheduler is not None:
        _scheduler.shutdown(wait=False)
        _scheduler = None
