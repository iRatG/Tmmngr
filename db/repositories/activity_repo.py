from datetime import datetime, timezone
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from db.models import ActivityLog


async def get_open_block(session: AsyncSession, user_id: int) -> ActivityLog | None:
    result = await session.execute(
        select(ActivityLog).where(
            ActivityLog.user_id == user_id,
            ActivityLog.status == "open",
        )
    )
    return result.scalar_one_or_none()


async def create_open_block(
    session: AsyncSession,
    user_id: int,
    category_id: int,
    date_local,
    start_at: datetime,
    description: str | None = None,
) -> ActivityLog:
    log = ActivityLog(
        user_id=user_id,
        category_id=category_id,
        date_local=date_local,
        start_at=start_at,
        status="open",
        source="telegram",
        description=description,
    )
    session.add(log)
    await session.flush()
    return log


async def close_block(
    session: AsyncSession, log_id: int, end_at: datetime
) -> ActivityLog | None:
    result = await session.execute(
        select(ActivityLog).where(ActivityLog.id == log_id)
    )
    log = result.scalar_one_or_none()
    if not log:
        return None

    log.end_at = end_at
    log.status = "closed"
    log.updated_at = datetime.now(timezone.utc)
    if log.start_at:
        delta = end_at - log.start_at
        log.duration_min = max(0, int(delta.total_seconds() / 60))
    await session.flush()
    return log


async def set_description(
    session: AsyncSession, log_id: int, description: str
) -> None:
    await session.execute(
        update(ActivityLog)
        .where(ActivityLog.id == log_id)
        .values(description=description, updated_at=datetime.now(timezone.utc))
    )
    await session.flush()
