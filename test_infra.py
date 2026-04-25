"""
Infrastructure smoke tests for TimeMirror.
Run inside the app container: python test_infra.py
"""
import asyncio
import sys

import httpx
from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine

from config import settings


EXPECTED_TABLES = {
    "users", "user_settings", "google_connections", "categories",
    "activity_logs", "sync_events", "daily_aggregates", "weekly_aggregates",
}

results = []


def ok(msg: str) -> None:
    print(f"  [OK] {msg}")
    results.append(True)


def fail(msg: str) -> None:
    print(f"  [FAIL] {msg}")
    results.append(False)


async def test_db_connection() -> None:
    print("\n--- DB connection ---")
    try:
        engine = create_async_engine(settings.database_url, pool_pre_ping=True)
        async with engine.connect() as conn:
            result = await conn.execute(text("SELECT version()"))
            version = result.scalar()
            ok(f"Connected: {version[:40]}")
        await engine.dispose()
    except Exception as e:
        fail(f"DB connection failed: {e}")


async def test_tables_exist() -> None:
    print("\n--- Tables ---")
    try:
        engine = create_async_engine(settings.database_url)
        async with engine.connect() as conn:
            result = await conn.execute(text(
                "SELECT tablename FROM pg_tables WHERE schemaname = 'public'"
            ))
            existing = {row[0] for row in result}
        await engine.dispose()

        for table in sorted(EXPECTED_TABLES):
            if table in existing:
                ok(table)
            else:
                fail(f"MISSING: {table}")
    except Exception as e:
        fail(f"Table check failed: {e}")


async def test_crud() -> None:
    print("\n--- CRUD (users table) ---")
    try:
        engine = create_async_engine(settings.database_url)
        async with engine.begin() as conn:
            # Insert
            await conn.execute(text(
                "INSERT INTO users (telegram_user_id, first_name, timezone, status) "
                "VALUES (999999999, 'TestUser', 'Europe/Moscow', 'active')"
            ))
            # Read
            result = await conn.execute(text(
                "SELECT first_name FROM users WHERE telegram_user_id = 999999999"
            ))
            row = result.fetchone()
            assert row and row[0] == "TestUser", "Read mismatch"
            ok("INSERT + SELECT")
            # Delete
            await conn.execute(text(
                "DELETE FROM users WHERE telegram_user_id = 999999999"
            ))
            ok("DELETE")
        await engine.dispose()
    except Exception as e:
        fail(f"CRUD failed: {e}")


def test_health_endpoint() -> None:
    print("\n--- Health endpoint ---")
    try:
        r = httpx.get("http://127.0.0.1:8000/health", timeout=5)
        assert r.status_code == 200, f"status {r.status_code}"
        assert r.json() == {"status": "ok"}, f"body {r.json()}"
        ok(f"GET /health → {r.json()}")
    except Exception as e:
        fail(f"Health check failed: {e}")


def test_config_loaded() -> None:
    print("\n--- Config ---")
    checks = [
        ("telegram_bot_token", bool(settings.telegram_bot_token)),
        ("database_url", "timemirror" in settings.database_url),
        ("deepseek_api_key", bool(settings.deepseek_api_key)),
        ("timezone_default", settings.timezone_default == "Europe/Moscow"),
    ]
    for name, passed in checks:
        ok(name) if passed else fail(name)


async def main() -> None:
    print("=" * 50)
    print("TimeMirror Infrastructure Tests")
    print("=" * 50)

    test_config_loaded()
    await test_db_connection()
    await test_tables_exist()
    await test_crud()
    test_health_endpoint()

    print("\n" + "=" * 50)
    passed = sum(results)
    total = len(results)
    print(f"Result: {passed}/{total} passed")
    print("=" * 50)

    sys.exit(0 if passed == total else 1)


if __name__ == "__main__":
    asyncio.run(main())
