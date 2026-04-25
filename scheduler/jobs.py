"""APScheduler job definitions."""
import logging

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger
from apscheduler.triggers.interval import IntervalTrigger
from aiogram import Bot

log = logging.getLogger(__name__)

_scheduler: AsyncIOScheduler | None = None


def get_scheduler() -> AsyncIOScheduler:
    global _scheduler
    if _scheduler is None:
        _scheduler = AsyncIOScheduler()
    return _scheduler


def setup_jobs(bot: Bot) -> AsyncIOScheduler:
    from services.reminder_service import send_open_block_reminders
    from services.analytics_service import build_daily_aggregates
    from services.summary_service import send_evening_reports, send_weekly_reports
    from services.sheets_sync_service import pull_corrections_all_users

    scheduler = get_scheduler()

    # Reminder: every minute, checks open blocks and fires at threshold
    scheduler.add_job(
        send_open_block_reminders,
        trigger=IntervalTrigger(minutes=1),
        args=[bot],
        id="reminders",
        replace_existing=True,
        misfire_grace_time=30,
    )

    # Daily aggregates: every night at 23:55 UTC
    scheduler.add_job(
        build_daily_aggregates,
        trigger=CronTrigger(hour=23, minute=55),
        id="daily_aggregates",
        replace_existing=True,
    )

    # Evening reports: 21:00 Moscow = 18:00 UTC
    scheduler.add_job(
        send_evening_reports,
        trigger=CronTrigger(hour=18, minute=0),
        args=[bot],
        id="evening_reports",
        replace_existing=True,
    )

    # Weekly reports: Sunday 20:00 Moscow = 17:00 UTC
    scheduler.add_job(
        send_weekly_reports,
        trigger=CronTrigger(day_of_week="sun", hour=17, minute=0),
        args=[bot],
        id="weekly_reports",
        replace_existing=True,
    )

    # Sheets pull: every 30 minutes
    scheduler.add_job(
        pull_corrections_all_users,
        trigger=IntervalTrigger(minutes=30),
        id="sheets_pull",
        replace_existing=True,
        misfire_grace_time=60,
    )

    return scheduler
