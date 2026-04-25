"""Onboarding: /start and Google Sheet connection flow."""
import asyncio
import logging

from aiogram import Router
from aiogram.filters import CommandStart
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import Message

from bot import keyboards as kb
from bot import messages as msg
from db.repositories.category_repo import get_user_categories, seed_default_categories
from db.repositories.user_repo import get_or_create_user, set_google_sheet_connected
from db.session import AsyncSessionFactory
from db.models import GoogleConnection
from integrations.google_sheets import (
    extract_spreadsheet_id,
    init_spreadsheet,
    write_categories_to_sheet,
)

log = logging.getLogger(__name__)
router = Router()


class OnboardingState(StatesGroup):
    waiting_for_sheet = State()


@router.message(CommandStart())
async def cmd_start(message: Message, state: FSMContext) -> None:
    async with AsyncSessionFactory() as session:
        async with session.begin():
            user, created = await get_or_create_user(
                session,
                telegram_user_id=message.from_user.id,
                first_name=message.from_user.first_name,
                telegram_username=message.from_user.username,
            )

    if not created:
        await message.answer(msg.ALREADY_REGISTERED, reply_markup=kb.main_menu_kb())
        await state.clear()
        return

    await message.answer(msg.WELCOME, parse_mode="HTML")
    await message.answer(msg.SHEET_PROMPT, parse_mode="HTML")
    await state.set_state(OnboardingState.waiting_for_sheet)
    await state.update_data(user_id=user.id)


@router.message(OnboardingState.waiting_for_sheet)
async def handle_sheet_link(message: Message, state: FSMContext) -> None:
    url = message.text or ""
    spreadsheet_id = extract_spreadsheet_id(url)

    if not spreadsheet_id:
        await message.answer(msg.SHEET_INVALID, parse_mode="HTML")
        return

    data = await state.get_data()
    user_id: int = data["user_id"]

    # Try connecting to the sheet (sync gspread → thread)
    try:
        await asyncio.to_thread(init_spreadsheet, spreadsheet_id)
    except Exception as e:
        log.warning("Sheet access error for user %d: %s", user_id, e)
        await message.answer(msg.SHEET_ACCESS_ERROR, parse_mode="HTML")
        return

    async with AsyncSessionFactory() as session:
        async with session.begin():
            # Save Google connection
            conn = GoogleConnection(
                user_id=user_id,
                spreadsheet_id=spreadsheet_id,
                spreadsheet_url=url.strip(),
                connection_status="active",
            )
            session.add(conn)

            # Mark sheet connected
            await set_google_sheet_connected(session, user_id, True)

            # Seed categories
            categories = await seed_default_categories(session, user_id)

    # Write categories to sheet (outside transaction, best-effort)
    try:
        cat_rows = [(c.id, c.name, c.is_active, c.sort_order) for c in categories]
        await asyncio.to_thread(write_categories_to_sheet, spreadsheet_id, cat_rows)
    except Exception as e:
        log.warning("Failed to write categories to sheet for user %d: %s", user_id, e)

    await state.clear()
    await message.answer(msg.SHEET_CONNECTED, parse_mode="HTML", reply_markup=kb.main_menu_kb())
