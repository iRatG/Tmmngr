"""Handlers for reminder inline keyboard callbacks."""
import logging

from aiogram import F, Router
from aiogram.types import CallbackQuery

from bot import keyboards as kb
from bot import messages as msg
from db.repositories.activity_repo import get_open_block
from db.repositories.user_repo import get_user_by_telegram_id
from db.session import AsyncSessionFactory
from services.activity_service import finish_block, sync_log_to_sheet

log = logging.getLogger(__name__)
router = Router()


@router.callback_query(F.data.startswith("reminder:"))
async def cb_reminder(callback: CallbackQuery) -> None:
    _, action, log_id_str = callback.data.split(":")
    log_id = int(log_id_str)

    if action == "running":
        await callback.message.edit_text("Хорошо, продолжай! 👍")
        await callback.answer()
        return

    if action == "later":
        await callback.message.edit_text(
            "Понял, исправь в Google Таблице когда будет удобно."
        )
        await callback.answer()
        return

    # action == "finish"
    async with AsyncSessionFactory() as session:
        user = await get_user_by_telegram_id(session, callback.from_user.id)
        if not user:
            await callback.answer(msg.ERROR_GENERIC)
            return

        open_log = await get_open_block(session, user.id)
        if not open_log or open_log.id != log_id:
            await callback.message.edit_text("Блок уже завершён.")
            await callback.answer()
            return

        async with AsyncSessionFactory() as sess2:
            async with sess2.begin():
                closed = await finish_block(sess2, user.id)

            if closed:
                from sqlalchemy import select
                from db.models import Category
                result = await sess2.execute(
                    select(Category).where(Category.id == closed.category_id)
                )
                cat = result.scalar_one_or_none()
                cat_name = cat.name if cat else "?"
                await sync_log_to_sheet(sess2, closed)

    if closed:
        await callback.message.edit_text(
            msg.BLOCK_FINISHED.format(
                category=cat_name, duration=closed.duration_min or 0
            ),
            parse_mode="HTML",
        )
    await callback.answer()
