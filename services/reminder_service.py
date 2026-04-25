"""Send reminder messages for open blocks."""
import logging
from datetime import datetime, timezone

from aiogram import Bot
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from bot import keyboards as kb
from bot import messages as msg
from db.models import ActivityLog, Category, User
from db.session import AsyncSessionFactory

log = logging.getLogger(__name__)


async def send_open_block_reminders(bot: Bot) -> None:
    """Called by scheduler. Sends reminder to each user with an open block."""
    async with AsyncSessionFactory() as session:
        result = await session.execute(
            select(ActivityLog, User, Category)
            .join(User, User.id == ActivityLog.user_id)
            .outerjoin(Category, Category.id == ActivityLog.category_id)
            .where(ActivityLog.status == "open")
        )
        rows = result.all()

    now = datetime.now(timezone.utc)
    for log_entry, user, category in rows:
        if not log_entry.start_at:
            continue

        elapsed_min = int((now - log_entry.start_at).total_seconds() / 60)

        # Only remind after the user's reminder_minutes threshold
        # Default 30 min; we check every minute so we only fire once per threshold
        async with AsyncSessionFactory() as session:
            from db.models import UserSettings
            settings_result = await session.execute(
                select(UserSettings).where(UserSettings.user_id == user.id)
            )
            settings = settings_result.scalar_one_or_none()

        threshold = settings.reminder_minutes if settings else 30

        # Fire at threshold, then every threshold minutes again
        if elapsed_min > 0 and elapsed_min % threshold == 0:
            cat_name = category.name if category else "?"
            try:
                await bot.send_message(
                    user.telegram_user_id,
                    msg.REMINDER_TEXT.format(
                        category=cat_name, elapsed=elapsed_min
                    ),
                    parse_mode="HTML",
                    reply_markup=kb.reminder_kb(log_entry.id),
                )
            except Exception as e:
                log.warning(
                    "Failed to send reminder to user %d: %s",
                    user.telegram_user_id,
                    e,
                )
