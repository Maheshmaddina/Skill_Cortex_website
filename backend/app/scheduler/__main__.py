"""Scheduler process — run exactly one: python -m app.scheduler

Kept out of the API process so multiple API workers don't each start their own scheduler.
"""

import logging
import signal
from datetime import datetime
from zoneinfo import ZoneInfo

from apscheduler.schedulers.blocking import BlockingScheduler
from apscheduler.triggers.interval import IntervalTrigger

import app.models  # noqa: F401
from app.scheduler.jobs import (
    complete_finished_bookings_job,
    dispatch_notifications_job,
    expire_stale_bookings_job,
    purge_rate_limits_job,
    send_reminders_job,
)

UTC = ZoneInfo("UTC")


def build_scheduler() -> BlockingScheduler:
    scheduler = BlockingScheduler(timezone=UTC, job_defaults={"coalesce": True, "max_instances": 1})
    now = datetime.now(UTC)
    for job, interval, job_id in (
        (expire_stale_bookings_job, IntervalTrigger(minutes=1), "expire_stale_bookings"),
        (dispatch_notifications_job, IntervalTrigger(minutes=1), "dispatch_notifications"),
        (send_reminders_job, IntervalTrigger(minutes=5), "send_reminders"),
        (complete_finished_bookings_job, IntervalTrigger(minutes=10), "complete_finished_bookings"),
        (purge_rate_limits_job, IntervalTrigger(hours=1), "purge_rate_limits"),
    ):
        scheduler.add_job(job, interval, id=job_id, next_run_time=now)
    return scheduler


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s [%(name)s] %(message)s")
    scheduler = build_scheduler()
    signal.signal(signal.SIGTERM, lambda *_: scheduler.shutdown(wait=False))
    logging.getLogger(__name__).info("Scheduler started with jobs: %s", [job.id for job in scheduler.get_jobs()])
    scheduler.start()


if __name__ == "__main__":
    main()
