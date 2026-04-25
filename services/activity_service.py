"""Business logic for activity blocks."""
import asyncio
import logging
from datetime import datetime, timezone, date

from sqlalchemy.ext.asyncio import AsyncSession

from db.models import ActivityLog, Category, GoogleConnection
from db.repositories.activity_repo import (
    close_block,
    create_open_block,
    get_open_block,
)
from db.repositories.category_repo import get_user_categories
from sqlalchemy import select
from integrations import google_sheets

log = logging.getLogger(__name__)


async def get_categories(session: AsyncSession, user_id: int) -> list[Category]:
    return await get_user_categories(session, user_id)


async def start_block(
    session: AsyncSession,
    user_id: int,
    category_id: int,
    description: str | None = None,
) -> ActivityLog:
    now = datetime.now(timezone.utc)
    log_entry = await create_open_block(
        session,
        user_id=user_id,
        category_id=category_id,
        date_local=date.today(),
        start_at=now,
        description=description,
    )
    return log_entry


async def finish_block(
    session: AsyncSession, user_id: int
) -> ActivityLog | None:
    open_log = await get_open_block(session, user_id)
    if not open_log:
        return None

    now = datetime.now(timezone.utc)
    closed = await close_block(session, open_log.id, now)

    # Best-effort: sync to Google Sheets after commit
    return closed


async def sync_log_to_sheet(session: AsyncSession, log_entry: ActivityLog) -> None:
    """Push a closed log row to Google Sheets. Call after transaction commit."""
    result = await session.execute(
        select(GoogleConnection).where(
            GoogleConnection.user_id == log_entry.user_id,
            GoogleConnection.connection_status == "active",
        )
    )
    conn = result.scalar_one_or_none()
    if not conn:
        return

    # Resolve category name
    cat_result = await session.execute(
        select(Category).where(Category.id == log_entry.category_id)
    )
    category = cat_result.scalar_one_or_none()
    cat_name = category.name if category else ""

    row = [
        log_entry.id,
        str(log_entry.date_local),
        log_entry.start_at.strftime("%H:%M") if log_entry.start_at else "",
        log_entry.end_at.strftime("%H:%M") if log_entry.end_at else "",
        log_entry.duration_min or 0,
        cat_name,
        log_entry.description or "",
        log_entry.status,
        str(log_entry.updated_at)[:19],
    ]

    try:
        await asyncio.to_thread(
            google_sheets.append_log_row, conn.spreadsheet_id, row
        )
    except Exception as e:
        log.warning("Sheet sync failed for log %d: %s", log_entry.id, e)
