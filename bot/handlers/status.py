"""Handler for 'Today' status button."""
import logging

from aiogram import F, Router
from aiogram.types import Message

from bot import keyboards as kb
from bot import messages as msg
from db.repositories.user_repo import get_user_by_telegram_id
from db.session import AsyncSessionFactory
from services.analytics_service import get_today_stats

log = logging.getLogger(__name__)
router = Router()


@router.message(F.text == "📊 Сегодня")
async def btn_today(message: Message) -> None:
    async with AsyncSessionFactory() as session:
        user = await get_user_by_telegram_id(session, message.from_user.id)
        if not user:
            await message.answer(msg.ERROR_GENERIC)
            return
        stats = await get_today_stats(session, user.id)

    if not stats["by_category"]:
        await message.answer(msg.TODAY_NO_LOGS)
        return

    lines = []
    for cat_name, mins in sorted(
        stats["by_category"].items(), key=lambda x: x[1], reverse=True
    ):
        h, m = divmod(mins, 60)
        time_str = f"{h}ч {m}мин" if h else f"{m}мин"
        lines.append(f"• {cat_name}: {time_str}")

    total = stats["total"]
    h, m = divmod(total, 60)
    total_str = f"{h}ч {m}мин" if h else f"{m}мин"

    text = msg.TODAY_SUMMARY.format(
        date=stats["date"].strftime("%d.%m.%Y"),
        lines="\n".join(lines),
        total=total_str,
    )
    await message.answer(text, parse_mode="HTML")
