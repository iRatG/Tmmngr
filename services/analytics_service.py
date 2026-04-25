"""Compute and store daily/weekly aggregates for all users."""
import logging
from datetime import date, datetime, timedelta, timezone

from sqlalchemy import select, func, delete
from sqlalchemy.ext.asyncio import AsyncSession

from db.models import ActivityLog, Category, DailyAggregate, User, WeeklyAggregate
from db.session import AsyncSessionFactory

log = logging.getLogger(__name__)

# Categories considered "study"
STUDY_KEYWORDS = {"школа", "домашка", "зфтш"}
REST_KEYWORDS = {"отдых", "сон", "кино", "чтение"}
HOBBY_KEYWORDS = {"монтаж видео", "футбол", "чтение"}


def _classify(cat_name: str) -> str:
    n = cat_name.lower()
    if n in STUDY_KEYWORDS:
        return "study"
    if n in REST_KEYWORDS:
        return "rest"
    if n in HOBBY_KEYWORDS:
        return "hobby"
    return "other"


async def _build_for_user(session: AsyncSession, user_id: int, target_date: date) -> None:
    # Fetch closed logs for that date
    result = await session.execute(
        select(ActivityLog, Category)
        .outerjoin(Category, Category.id == ActivityLog.category_id)
        .where(
            ActivityLog.user_id == user_id,
            ActivityLog.date_local == target_date,
            ActivityLog.status == "closed",
        )
    )
    rows = result.all()

    total = study = rest = hobby = 0
    blocks = len(rows)
    for log_entry, category in rows:
        mins = log_entry.duration_min or 0
        total += mins
        if category:
            kind = _classify(category.name)
            if kind == "study":
                study += mins
            elif kind == "rest":
                rest += mins
            elif kind == "hobby":
                hobby += mins

    # Count open blocks (shouldn't happen but track anyway)
    open_result = await session.execute(
        select(func.count()).where(
            ActivityLog.user_id == user_id,
            ActivityLog.date_local == target_date,
            ActivityLog.status == "open",
        )
    )
    open_blocks = open_result.scalar_one()

    # Upsert DailyAggregate
    existing = await session.execute(
        select(DailyAggregate).where(
            DailyAggregate.user_id == user_id,
            DailyAggregate.date_local == target_date,
        )
    )
    agg = existing.scalar_one_or_none()
    if agg:
        agg.total_minutes = total
        agg.study_minutes = study
        agg.rest_minutes = rest
        agg.hobby_minutes = hobby
        agg.blocks_count = blocks
        agg.open_blocks_count = open_blocks
    else:
        agg = DailyAggregate(
            user_id=user_id,
            date_local=target_date,
            total_minutes=total,
            study_minutes=study,
            rest_minutes=rest,
            hobby_minutes=hobby,
            blocks_count=blocks,
            open_blocks_count=open_blocks,
        )
        session.add(agg)
    await session.flush()


async def build_daily_aggregates() -> None:
    """Called by scheduler at 23:55. Builds aggregates for today for all users."""
    today = datetime.now(timezone.utc).date()
    async with AsyncSessionFactory() as session:
        users_result = await session.execute(select(User.id))
        user_ids = [row[0] for row in users_result.all()]

    for user_id in user_ids:
        try:
            async with AsyncSessionFactory() as session:
                async with session.begin():
                    await _build_for_user(session, user_id, today)
        except Exception as e:
            log.error("Failed daily aggregate for user %d: %s", user_id, e)


async def get_today_stats(session: AsyncSession, user_id: int) -> dict:
    """Return today's stats dict for display."""
    today = datetime.now(timezone.utc).date()

    result = await session.execute(
        select(ActivityLog, Category)
        .outerjoin(Category, Category.id == ActivityLog.category_id)
        .where(
            ActivityLog.user_id == user_id,
            ActivityLog.date_local == today,
            ActivityLog.status == "closed",
        )
    )
    rows = result.all()

    by_category: dict[str, int] = {}
    total = 0
    for log_entry, category in rows:
        mins = log_entry.duration_min or 0
        total += mins
        name = category.name if category else "без категории"
        by_category[name] = by_category.get(name, 0) + mins

    return {"date": today, "total": total, "by_category": by_category}


async def get_week_stats(session: AsyncSession, user_id: int) -> dict:
    """Return last 7 days stats dict."""
    today = datetime.now(timezone.utc).date()
    week_ago = today - timedelta(days=6)

    result = await session.execute(
        select(ActivityLog, Category)
        .outerjoin(Category, Category.id == ActivityLog.category_id)
        .where(
            ActivityLog.user_id == user_id,
            ActivityLog.date_local >= week_ago,
            ActivityLog.status == "closed",
        )
    )
    rows = result.all()

    by_category: dict[str, int] = {}
    total = 0
    for log_entry, category in rows:
        mins = log_entry.duration_min or 0
        total += mins
        name = category.name if category else "без категории"
        by_category[name] = by_category.get(name, 0) + mins

    top = sorted(by_category.items(), key=lambda x: x[1], reverse=True)[:5]
    return {
        "week_start": week_ago,
        "week_end": today,
        "total": total,
        "by_category": by_category,
        "top": top,
    }
