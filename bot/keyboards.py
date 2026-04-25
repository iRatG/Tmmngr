from aiogram.types import ReplyKeyboardMarkup, KeyboardButton, InlineKeyboardMarkup
from aiogram.utils.keyboard import ReplyKeyboardBuilder, InlineKeyboardBuilder

from db.models import Category


def main_menu_kb() -> ReplyKeyboardMarkup:
    builder = ReplyKeyboardBuilder()
    builder.row(
        KeyboardButton(text="▶️ Начать блок"),
        KeyboardButton(text="⏹ Завершить блок"),
    )
    builder.row(
        KeyboardButton(text="📊 Сегодня"),
        KeyboardButton(text="📋 Категории"),
        KeyboardButton(text="⚙️ Настройки"),
    )
    return builder.as_markup(resize_keyboard=True)


def categories_kb(categories: list[Category]) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    for cat in categories:
        builder.button(text=cat.name, callback_data=f"cat:{cat.id}")
    builder.adjust(2)
    return builder.as_markup()


def reminder_kb(log_id: int) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.button(text="▶️ Ещё идёт", callback_data=f"reminder:running:{log_id}")
    builder.button(text="⏹ Завершить", callback_data=f"reminder:finish:{log_id}")
    builder.button(text="✏️ Исправлю позже", callback_data=f"reminder:later:{log_id}")
    builder.adjust(1)
    return builder.as_markup()


def confirm_finish_kb(log_id: int) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.button(text="✅ Завершить", callback_data=f"finish:{log_id}")
    builder.button(text="❌ Отмена", callback_data="finish:cancel")
    builder.adjust(2)
    return builder.as_markup()


def skip_description_kb() -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.button(text="Пропустить", callback_data="desc:skip")
    return builder.as_markup()
