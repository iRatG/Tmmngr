"""Settings and Categories info handlers."""
import logging

from aiogram import F, Router
from aiogram.types import Message, CallbackQuery
from aiogram.utils.keyboard import InlineKeyboardBuilder

from db.repositories.category_repo import get_user_categories
from db.repositories.user_repo import get_user_by_telegram_id
from db.session import AsyncSessionFactory
from services.sheets_sync_service import pull_corrections_for_user

log = logging.getLogger(__name__)
router = Router()


@router.message(F.text == "📋 Категории")
async def btn_categories(message: Message) -> None:
    async with AsyncSessionFactory() as session:
        user = await get_user_by_telegram_id(session, message.from_user.id)
        if not user:
            await message.answer("Сначала нажми /start.")
            return
        cats = await get_user_categories(session, user.id)

    if not cats:
        await message.answer("Категорий пока нет.")
        return

    lines = [f"{i+1}. {c.name}" for i, c in enumerate(cats)]
    await message.answer(
        "<b>Твои категории:</b>\n\n" + "\n".join(lines),
        parse_mode="HTML",
    )


@router.message(F.text == "⚙️ Настройки")
async def btn_settings(message: Message) -> None:
    async with AsyncSessionFactory() as session:
        user = await get_user_by_telegram_id(session, message.from_user.id)
        if not user:
            await message.answer("Сначала нажми /start.")
            return

        from sqlalchemy import select
        from db.models import UserSettings, GoogleConnection
        settings_res = await session.execute(
            select(UserSettings).where(UserSettings.user_id == user.id)
        )
        settings = settings_res.scalar_one_or_none()

        conn_res = await session.execute(
            select(GoogleConnection).where(
                GoogleConnection.user_id == user.id,
                GoogleConnection.connection_status == "active",
            )
        )
        conn = conn_res.scalar_one_or_none()

    reminder = settings.reminder_minutes if settings else 30
    evening = "вкл" if (settings and settings.evening_report_enabled) else "выкл"
    weekly = "вкл" if (settings and settings.weekly_report_enabled) else "выкл"
    sheet = conn.spreadsheet_url if conn else "не подключена"

    builder = InlineKeyboardBuilder()
    builder.button(text="🔄 Синхронизировать таблицу", callback_data="settings:sync")
    builder.adjust(1)

    text = (
        "<b>Настройки</b>\n\n"
        f"⏰ Напоминание через: <b>{reminder} мин</b>\n"
        f"🌙 Вечерний отчёт: <b>{evening}</b>\n"
        f"📅 Недельный отчёт: <b>{weekly}</b>\n"
        f"📊 Таблица: <b>{sheet[:60] if len(sheet) > 60 else sheet}</b>"
    )
    await message.answer(text, parse_mode="HTML", reply_markup=builder.as_markup())


@router.callback_query(F.data == "settings:sync")
async def cb_sync_sheet(callback: CallbackQuery) -> None:
    await callback.answer("Синхронизирую...")

    async with AsyncSessionFactory() as session:
        user = await get_user_by_telegram_id(session, callback.from_user.id)
        if not user:
            await callback.message.edit_text("Сначала нажми /start.")
            return

    count = await pull_corrections_for_user(user.id)
    if count:
        await callback.message.edit_text(
            f"✅ Синхронизация завершена. Применено правок: <b>{count}</b>",
            parse_mode="HTML",
        )
    else:
        await callback.message.edit_text("✅ Синхронизация завершена. Новых правок нет.")
