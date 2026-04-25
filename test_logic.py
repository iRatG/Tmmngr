"""
Business logic tests for TimeMirror sessions 3-6.
Run inside app container: python test_logic.py
"""
import asyncio
import sys
from datetime import datetime, timezone, timedelta, date

results = []


def ok(msg: str) -> None:
    print(f"  [OK] {msg}")
    results.append(True)


def fail(msg: str) -> None:
    print(f"  [FAIL] {msg}")
    results.append(False)


# ── 1. Google Sheets: extract_spreadsheet_id ─────────────────────────────────

def test_extract_spreadsheet_id() -> None:
    print("\n--- extract_spreadsheet_id ---")
    from integrations.google_sheets import extract_spreadsheet_id

    cases = [
        ("https://docs.google.com/spreadsheets/d/ABC123xyz/edit#gid=0", "ABC123xyz"),
        ("https://docs.google.com/spreadsheets/d/1BxiMVs0XRA5nFMdKvBdBZjgmUUqptlbs74OgVE2upms/edit", "1BxiMVs0XRA5nFMdKvBdBZjgmUUqptlbs74OgVE2upms"),
        ("not a url", None),
        ("https://docs.google.com/spreadsheets/d/XYZ-_123/pub", "XYZ-_123"),
    ]
    for url, expected in cases:
        got = extract_spreadsheet_id(url)
        if got == expected:
            ok(f"'{url[:40]}...' → {got}")
        else:
            fail(f"expected {expected}, got {got}")


# ── 2. Analytics: category classification ────────────────────────────────────

def test_category_classify() -> None:
    print("\n--- category classification ---")
    from services.analytics_service import _classify

    cases = [
        ("школа", "study"),
        ("домашка", "study"),
        ("ЗФТШ", "study"),
        ("отдых", "rest"),
        ("сон", "rest"),
        ("футбол", "hobby"),
        ("монтаж видео", "hobby"),
        ("дорога", "other"),
        ("телефон", "other"),
    ]
    for name, expected in cases:
        got = _classify(name)
        if got == expected:
            ok(f"'{name}' → {got}")
        else:
            fail(f"'{name}': expected {expected}, got {got}")


# ── 3. DB: user creation + activity flow ─────────────────────────────────────

async def test_user_and_activity() -> None:
    print("\n--- user creation + activity flow ---")
    from db.session import AsyncSessionFactory
    from db.repositories.user_repo import get_or_create_user, get_user_by_telegram_id
    from db.repositories.category_repo import seed_default_categories, get_user_categories
    from db.repositories.activity_repo import (
        create_open_block, get_open_block, close_block
    )

    TEST_TG_ID = 777000777

    # Cleanup from previous run (respect FK order)
    async with AsyncSessionFactory() as session:
        async with session.begin():
            from sqlalchemy import text
            for stmt in [
                "DELETE FROM activity_logs WHERE user_id IN (SELECT id FROM users WHERE telegram_user_id = :tid)",
                "DELETE FROM daily_aggregates WHERE user_id IN (SELECT id FROM users WHERE telegram_user_id = :tid)",
                "DELETE FROM categories WHERE user_id IN (SELECT id FROM users WHERE telegram_user_id = :tid)",
                "DELETE FROM user_settings WHERE user_id IN (SELECT id FROM users WHERE telegram_user_id = :tid)",
                "DELETE FROM users WHERE telegram_user_id = :tid",
            ]:
                await session.execute(text(stmt), {"tid": TEST_TG_ID})

    # Create user
    async with AsyncSessionFactory() as session:
        async with session.begin():
            user, created = await get_or_create_user(
                session,
                telegram_user_id=TEST_TG_ID,
                first_name="TestUser",
                telegram_username="testuser",
            )
    if created and user.id:
        ok(f"user created, id={user.id}")
    else:
        fail("user creation failed")
        return

    # Second call should return existing
    async with AsyncSessionFactory() as session:
        async with session.begin():
            user2, created2 = await get_or_create_user(
                session,
                telegram_user_id=TEST_TG_ID,
                first_name="TestUser",
                telegram_username="testuser",
            )
    if not created2 and user2.id == user.id:
        ok("idempotent: second get_or_create returns same user")
    else:
        fail(f"expected created2=False and same id, got created2={created2}")

    # Seed categories
    async with AsyncSessionFactory() as session:
        async with session.begin():
            cats = await seed_default_categories(session, user.id)
    if len(cats) == 12:
        ok(f"12 default categories seeded")
    else:
        fail(f"expected 12 categories, got {len(cats)}")

    # Get categories
    async with AsyncSessionFactory() as session:
        cats2 = await get_user_categories(session, user.id)
    if len(cats2) == 12 and cats2[0].sort_order == 1:
        ok("get_user_categories returns sorted list")
    else:
        fail(f"expected 12 sorted cats, got {len(cats2)}")

    # No open block initially
    async with AsyncSessionFactory() as session:
        open_block = await get_open_block(session, user.id)
    if open_block is None:
        ok("no open block initially")
    else:
        fail("unexpected open block")

    # Create open block
    cat_id = cats[0].id  # школа
    start_time = datetime.now(timezone.utc) - timedelta(minutes=45)
    async with AsyncSessionFactory() as session:
        async with session.begin():
            log_entry = await create_open_block(
                session,
                user_id=user.id,
                category_id=cat_id,
                date_local=date.today(),
                start_at=start_time,
                description="тест",
            )
    if log_entry.id and log_entry.status == "open":
        ok(f"open block created, id={log_entry.id}")
    else:
        fail("open block creation failed")

    # get_open_block returns it
    async with AsyncSessionFactory() as session:
        found = await get_open_block(session, user.id)
    if found and found.id == log_entry.id:
        ok("get_open_block finds the block")
    else:
        fail("get_open_block did not find block")

    # Close block
    end_time = datetime.now(timezone.utc)
    async with AsyncSessionFactory() as session:
        async with session.begin():
            closed = await close_block(session, log_entry.id, end_time)
    if closed and closed.status == "closed" and closed.duration_min and closed.duration_min >= 44:
        ok(f"block closed, duration={closed.duration_min} min")
    else:
        fail(f"close_block failed: status={closed.status if closed else None}, duration={closed.duration_min if closed else None}")

    # No open block after close
    async with AsyncSessionFactory() as session:
        open_after = await get_open_block(session, user.id)
    if open_after is None:
        ok("no open block after close")
    else:
        fail("open block still present after close")


# ── 4. Analytics: get_today_stats ────────────────────────────────────────────

async def test_today_stats() -> None:
    print("\n--- get_today_stats ---")
    from db.session import AsyncSessionFactory
    from db.repositories.user_repo import get_user_by_telegram_id
    from services.analytics_service import get_today_stats

    TEST_TG_ID = 777000777

    async with AsyncSessionFactory() as session:
        user = await get_user_by_telegram_id(session, TEST_TG_ID)
        if not user:
            fail("test user not found")
            return
        stats = await get_today_stats(session, user.id)

    if stats["total"] >= 44:
        ok(f"today total = {stats['total']} min")
    else:
        fail(f"expected >=44 min, got {stats['total']}")

    if stats["by_category"]:
        ok(f"by_category: {stats['by_category']}")
    else:
        fail("by_category is empty")


# ── 5. Analytics: build_daily_aggregates ─────────────────────────────────────

async def test_build_aggregates() -> None:
    print("\n--- build_daily_aggregates ---")
    from services.analytics_service import build_daily_aggregates
    from db.session import AsyncSessionFactory
    from db.models import DailyAggregate
    from db.repositories.user_repo import get_user_by_telegram_id
    from sqlalchemy import select

    TEST_TG_ID = 777000777

    try:
        await build_daily_aggregates()
        ok("build_daily_aggregates ran without error")
    except Exception as e:
        fail(f"build_daily_aggregates raised: {e}")
        return

    async with AsyncSessionFactory() as session:
        user = await get_user_by_telegram_id(session, TEST_TG_ID)
        result = await session.execute(
            select(DailyAggregate).where(
                DailyAggregate.user_id == user.id,
                DailyAggregate.date_local == date.today(),
            )
        )
        agg = result.scalar_one_or_none()

    if agg and agg.total_minutes >= 44:
        ok(f"DailyAggregate created: total={agg.total_minutes}, study={agg.study_minutes}")
    else:
        fail(f"DailyAggregate missing or wrong: {agg}")


# ── 6. Cleanup ────────────────────────────────────────────────────────────────

async def cleanup() -> None:
    from db.session import AsyncSessionFactory
    from sqlalchemy import text
    async with AsyncSessionFactory() as session:
        async with session.begin():
            await session.execute(text(
                "DELETE FROM activity_logs WHERE user_id IN "
                "(SELECT id FROM users WHERE telegram_user_id = 777000777)"
            ))
            await session.execute(text(
                "DELETE FROM daily_aggregates WHERE user_id IN "
                "(SELECT id FROM users WHERE telegram_user_id = 777000777)"
            ))
            await session.execute(text(
                "DELETE FROM categories WHERE user_id IN "
                "(SELECT id FROM users WHERE telegram_user_id = 777000777)"
            ))
            await session.execute(text(
                "DELETE FROM user_settings WHERE user_id IN "
                "(SELECT id FROM users WHERE telegram_user_id = 777000777)"
            ))
            await session.execute(text(
                "DELETE FROM users WHERE telegram_user_id = 777000777"
            ))


# ── Main ──────────────────────────────────────────────────────────────────────

async def main() -> None:
    print("=" * 50)
    print("TimeMirror Logic Tests")
    print("=" * 50)

    test_extract_spreadsheet_id()
    test_category_classify()
    await test_user_and_activity()
    await test_today_stats()
    await test_build_aggregates()
    await cleanup()

    print("\n" + "=" * 50)
    passed = sum(results)
    total = len(results)
    print(f"Result: {passed}/{total} passed")
    print("=" * 50)
    sys.exit(0 if passed == total else 1)


if __name__ == "__main__":
    asyncio.run(main())
