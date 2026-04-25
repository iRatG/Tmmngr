from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from db.models import Category

DEFAULT_CATEGORIES = [
    "школа",
    "домашка",
    "ЗФТШ",
    "отдых",
    "чтение",
    "кино",
    "монтаж видео",
    "футбол",
    "дорога",
    "семья",
    "телефон",
    "сон",
]


async def seed_default_categories(
    session: AsyncSession, user_id: int
) -> list[Category]:
    categories = [
        Category(user_id=user_id, name=name, sort_order=i + 1)
        for i, name in enumerate(DEFAULT_CATEGORIES)
    ]
    session.add_all(categories)
    await session.flush()
    return categories


async def get_user_categories(
    session: AsyncSession, user_id: int
) -> list[Category]:
    result = await session.execute(
        select(Category)
        .where(Category.user_id == user_id, Category.is_active == True)
        .order_by(Category.sort_order)
    )
    return list(result.scalars().all())
