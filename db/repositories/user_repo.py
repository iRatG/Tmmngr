from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from db.models import User, UserSettings


async def get_user_by_telegram_id(
    session: AsyncSession, telegram_user_id: int
) -> User | None:
    result = await session.execute(
        select(User).where(User.telegram_user_id == telegram_user_id)
    )
    return result.scalar_one_or_none()


async def get_or_create_user(
    session: AsyncSession,
    telegram_user_id: int,
    first_name: str | None,
    telegram_username: str | None,
    timezone: str = "Europe/Moscow",
) -> tuple[User, bool]:
    """Return (user, created). Flushes but does not commit."""
    user = await get_user_by_telegram_id(session, telegram_user_id)
    if user:
        return user, False

    user = User(
        telegram_user_id=telegram_user_id,
        first_name=first_name,
        telegram_username=telegram_username,
        timezone=timezone,
        status="active",
    )
    session.add(user)
    await session.flush()

    settings = UserSettings(user_id=user.id)
    session.add(settings)
    await session.flush()

    return user, True


async def set_google_sheet_connected(
    session: AsyncSession, user_id: int, connected: bool = True
) -> None:
    result = await session.execute(
        select(UserSettings).where(UserSettings.user_id == user_id)
    )
    settings = result.scalar_one_or_none()
    if settings:
        settings.google_sheet_connected = connected
        await session.flush()
