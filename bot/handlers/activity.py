"""Handlers for start/finish block flow."""
import logging

from aiogram import F, Router
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import CallbackQuery, Message

from bot import keyboards as kb
from bot import messages as msg
from db.repositories.activity_repo import get_open_block, set_description
from db.repositories.user_repo import get_user_by_telegram_id
from db.session import AsyncSessionFactory
from services.activity_service import (
    finish_block,
    get_categories,
    start_block,
    sync_log_to_sheet,
)

log = logging.getLogger(__name__)
router = Router()


class ActivityState(StatesGroup):
    choosing_category = State()
    entering_description = State()


# ── "Начать блок" button ──────────────────────────────────────────────────────

@router.message(F.text == "▶️ Начать блок")
async def btn_start_block(message: Message, state: FSMContext) -> None:
    async with AsyncSessionFactory() as session:
        user = await get_user_by_telegram_id(session, message.from_user.id)
        if not user:
            await message.answer(msg.ERROR_GENERIC)
            return

        open_log = await get_open_block(session, user.id)
        if open_log:
            # Resolve category name for the open block
            from sqlalchemy import select
            from db.models import Category
            result = await session.execute(
                select(Category).where(Category.id == open_log.category_id)
            )
            cat = result.scalar_one_or_none()
            cat_name = cat.name if cat else "?"
            await message.answer(
                msg.BLOCK_ALREADY_OPEN.format(category=cat_name),
                parse_mode="HTML",
            )
            return

        categories = await get_categories(session, user.id)

    if not categories:
        await message.answer(msg.NO_CATEGORIES)
        return

    await state.set_state(ActivityState.choosing_category)
    await state.update_data(user_id=user.id)
    await message.answer(msg.CHOOSE_CATEGORY, reply_markup=kb.categories_kb(categories))


# ── Category selected ─────────────────────────────────────────────────────────

@router.callback_query(ActivityState.choosing_category, F.data.startswith("cat:"))
async def cb_category_chosen(callback: CallbackQuery, state: FSMContext) -> None:
    category_id = int(callback.data.split(":")[1])
    data = await state.get_data()
    user_id: int = data["user_id"]

    # Resolve name for display
    async with AsyncSessionFactory() as session:
        from sqlalchemy import select
        from db.models import Category
        result = await session.execute(
            select(Category).where(Category.id == category_id)
        )
        cat = result.scalar_one_or_none()

    cat_name = cat.name if cat else "?"
    await state.update_data(category_id=category_id, category_name=cat_name)
    await state.set_state(ActivityState.entering_description)

    await callback.message.edit_text(
        msg.BLOCK_STARTED.format(category=cat_name),
        parse_mode="HTML",
        reply_markup=kb.skip_description_kb(),
    )
    await callback.answer()


# ── Description entered ───────────────────────────────────────────────────────

@router.message(ActivityState.entering_description)
async def msg_description(message: Message, state: FSMContext) -> None:
    data = await state.get_data()
    await _create_block(message, state, data, description=message.text.strip())


@router.callback_query(ActivityState.entering_description, F.data == "desc:skip")
async def cb_skip_description(callback: CallbackQuery, state: FSMContext) -> None:
    data = await state.get_data()
    await _create_block(callback.message, state, data, description=None)
    await callback.answer()


async def _create_block(
    message: Message,
    state: FSMContext,
    data: dict,
    description: str | None,
) -> None:
    user_id: int = data["user_id"]
    category_id: int = data["category_id"]
    cat_name: str = data["category_name"]

    async with AsyncSessionFactory() as session:
        async with session.begin():
            await start_block(session, user_id, category_id, description)

    await state.clear()
    await message.answer(
        msg.BLOCK_STARTED_NO_DESC.format(category=cat_name),
        parse_mode="HTML",
        reply_markup=kb.main_menu_kb(),
    )


# ── "Завершить блок" button ───────────────────────────────────────────────────

@router.message(F.text == "⏹ Завершить блок")
async def btn_finish_block(message: Message, state: FSMContext) -> None:
    await state.clear()

    async with AsyncSessionFactory() as session:
        user = await get_user_by_telegram_id(session, message.from_user.id)
        if not user:
            await message.answer(msg.ERROR_GENERIC)
            return

        open_log = await get_open_block(session, user.id)
        if not open_log:
            await message.answer(msg.NO_OPEN_BLOCK)
            return

        from sqlalchemy import select
        from db.models import Category
        result = await session.execute(
            select(Category).where(Category.id == open_log.category_id)
        )
        cat = result.scalar_one_or_none()
        cat_name = cat.name if cat else "?"

    await message.answer(
        f"Завершить блок <b>{cat_name}</b>?",
        parse_mode="HTML",
        reply_markup=kb.confirm_finish_kb(open_log.id),
    )


@router.callback_query(F.data.startswith("finish:"))
async def cb_finish_confirm(callback: CallbackQuery) -> None:
    parts = callback.data.split(":")
    if parts[1] == "cancel":
        await callback.message.edit_text("Отменено.")
        await callback.answer()
        return

    async with AsyncSessionFactory() as session:
        user = await get_user_by_telegram_id(session, callback.from_user.id)
        if not user:
            await callback.answer(msg.ERROR_GENERIC)
            return

        async with session.begin():
            closed = await finish_block(session, user.id)

        if not closed:
            await callback.message.edit_text(msg.NO_OPEN_BLOCK)
            await callback.answer()
            return

        # Resolve category for display
        from sqlalchemy import select
        from db.models import Category
        result = await session.execute(
            select(Category).where(Category.id == closed.category_id)
        )
        cat = result.scalar_one_or_none()
        cat_name = cat.name if cat else "?"

        # Sync to sheets (best-effort, after commit)
        await sync_log_to_sheet(session, closed)

    await callback.message.edit_text(
        msg.BLOCK_FINISHED.format(category=cat_name, duration=closed.duration_min or 0),
        parse_mode="HTML",
    )
    await callback.answer()
