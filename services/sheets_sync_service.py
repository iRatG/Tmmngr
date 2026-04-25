"""Pull manual corrections from Google Sheets back into PostgreSQL."""
import asyncio
import logging
from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from config import settings
from db.models import ActivityLog, Category, GoogleConnection, SyncEvent, User
from db.session import AsyncSessionFactory
from integrations import google_sheets

log = logging.getLogger(__name__)


async def _get_active_connections(session: AsyncSession) -> list[GoogleConnection]:
    result = await session.execute(
        select(GoogleConnection).where(
            GoogleConnection.connection_status == "active"
        )
    )
    return list(result.scalars().all())


async def _pull_for_user(
    session: AsyncSession,
    conn: GoogleConnection,
    user: User,
) -> int:
    """Read logs sheet and apply corrections. Returns number of rows updated."""
    try:
        rows = await asyncio.to_thread(
            google_sheets.read_logs_sheet, conn.spreadsheet_id
        )
    except Exception as e:
        log.warning("Failed to read sheet for user %d: %s", user.id, e)
        return 0

    updated = 0
    for row in rows:
        log_id = row.get("log_id")
        if not log_id:
            continue

        try:
            log_id = int(log_id)
        except (ValueError, TypeError):
            continue

        result = await session.execute(
            select(ActivityLog).where(
                ActivityLog.id == log_id,
                ActivityLog.user_id == user.id,
            )
        )
        entry = result.scalar_one_or_none()
        if not entry:
            continue

        changed = False

        # Check category correction
        sheet_category = (row.get("category") or "").strip()
        if sheet_category:
            cat_result = await session.execute(
                select(Category).where(
                    Category.user_id == user.id,
                    Category.name == sheet_category,
                    Category.is_active == True,
                )
            )
            cat = cat_result.scalar_one_or_none()
            if cat and cat.id != entry.category_id:
                entry.category_id = cat.id
                changed = True

        # Check description correction
        sheet_desc = row.get("description")
        if sheet_desc is not None and sheet_desc.strip() != (entry.description or ""):
            entry.description = sheet_desc.strip() or None
            changed = True

        # Check start_at correction (format HH:MM, same date)
        sheet_start = (row.get("start_at") or "").strip()
        if sheet_start and entry.date_local:
            try:
                h, m = map(int, sheet_start.split(":"))
                new_start = datetime(
                    entry.date_local.year,
                    entry.date_local.month,
                    entry.date_local.day,
                    h, m,
                    tzinfo=timezone.utc,
                )
                if abs((new_start - entry.start_at).total_seconds()) > 60:
                    entry.start_at = new_start
                    changed = True
            except (ValueError, AttributeError):
                pass

        # Check end_at correction
        sheet_end = (row.get("end_at") or "").strip()
        if sheet_end and entry.date_local and entry.end_at:
            try:
                h, m = map(int, sheet_end.split(":"))
                new_end = datetime(
                    entry.date_local.year,
                    entry.date_local.month,
                    entry.date_local.day,
                    h, m,
                    tzinfo=timezone.utc,
                )
                if abs((new_end - entry.end_at).total_seconds()) > 60:
                    entry.end_at = new_end
                    changed = True
            except (ValueError, AttributeError):
                pass

        if changed:
            entry.status = "corrected"
            entry.updated_at = datetime.now(timezone.utc)
            if entry.start_at and entry.end_at:
                delta = entry.end_at - entry.start_at
                entry.duration_min = max(0, int(delta.total_seconds() / 60))

            # Record sync event
            session.add(SyncEvent(
                user_id=user.id,
                entity_type="activity_log",
                entity_id=entry.id,
                sync_direction="pull",
                sync_status="applied",
                payload_json={
                    "category": sheet_category,
                    "description": sheet_desc,
                    "start_at": sheet_start,
                    "end_at": sheet_end,
                },
            ))
            updated += 1

    await session.flush()
    return updated


async def _pull_categories_for_user(
    session: AsyncSession,
    conn: GoogleConnection,
    user: User,
) -> int:
    """Read categories sheet and create new categories not yet in DB. Returns count added."""
    try:
        rows = await asyncio.to_thread(
            google_sheets.read_categories_sheet, conn.spreadsheet_id
        )
    except Exception as e:
        log.warning("Failed to read categories sheet for user %d: %s", user.id, e)
        return 0

    existing_result = await session.execute(
        select(Category).where(Category.user_id == user.id)
    )
    existing = {cat.name.lower(): cat for cat in existing_result.scalars().all()}

    added = 0
    for row in rows:
        name = (row.get("name") or "").strip()
        if not name or name.lower() in existing:
            continue
        new_cat = Category(
            user_id=user.id,
            name=name,
            is_active=True,
            sort_order=len(existing) + added + 1,
        )
        session.add(new_cat)
        added += 1

    if added:
        await session.flush()
        all_result = await session.execute(
            select(Category).where(Category.user_id == user.id).order_by(Category.sort_order)
        )
        all_cats = list(all_result.scalars().all())
        cat_rows = [(c.id, c.name, c.is_active, c.sort_order) for c in all_cats]
        try:
            await asyncio.to_thread(
                google_sheets.write_categories_to_sheet, conn.spreadsheet_id, cat_rows
            )
        except Exception as e:
            log.warning("Failed to write categories back to sheet for user %d: %s", user.id, e)

    return added


async def pull_corrections_for_user(user_id: int) -> int:
    """Pull corrections for a single user. Returns count of updated rows."""
    async with AsyncSessionFactory() as session:
        conn_result = await session.execute(
            select(GoogleConnection, User)
            .join(User, User.id == GoogleConnection.user_id)
            .where(
                GoogleConnection.user_id == user_id,
                GoogleConnection.connection_status == "active",
            )
        )
        row = conn_result.one_or_none()

    if not row:
        return 0

    conn, user = row
    async with AsyncSessionFactory() as session:
        async with session.begin():
            count_logs = await _pull_for_user(session, conn, user)
            count_cats = await _pull_categories_for_user(session, conn, user)
            count = count_logs + count_cats
            if count > 0:
                conn_obj = await session.get(GoogleConnection, conn.id)
                if conn_obj:
                    conn_obj.last_pull_at = datetime.now(timezone.utc)

    return count


async def pull_corrections_all_users() -> None:
    """Scheduler job: pull corrections for all active users."""
    async with AsyncSessionFactory() as session:
        result = await session.execute(
            select(GoogleConnection.user_id).where(
                GoogleConnection.connection_status == "active"
            )
        )
        user_ids = [row[0] for row in result.all()]

    for uid in user_ids:
        try:
            count = await pull_corrections_for_user(uid)
            if count:
                log.info("Pulled %d corrections for user %d", count, uid)
        except Exception as e:
            log.error("Sync pull failed for user %d: %s", uid, e)
