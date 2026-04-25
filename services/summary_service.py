"""Generate AI summaries via DeepSeek and send to users."""
import logging
from datetime import datetime, timezone

from aiogram import Bot
from openai import AsyncOpenAI
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from config import settings
from db.models import User, UserSettings, WeeklyAggregate
from db.session import AsyncSessionFactory
from services.analytics_service import get_today_stats, get_week_stats

log = logging.getLogger(__name__)


def _deepseek_client() -> AsyncOpenAI:
    return AsyncOpenAI(
        api_key=settings.deepseek_api_key,
        base_url=settings.deepseek_base_url,
    )


def _format_by_category(by_category: dict[str, int]) -> str:
    if not by_category:
        return "нет данных"
    lines = []
    for name, mins in sorted(by_category.items(), key=lambda x: x[1], reverse=True):
        h, m = divmod(mins, 60)
        lines.append(f"  • {name}: {h}ч {m}мин" if h else f"  • {name}: {m}мин")
    return "\n".join(lines)


async def _ai_daily_summary(stats: dict) -> str:
    prompt = (
        "Ты помощник по учёту времени. Дай краткий (3–5 строк) спокойный комментарий "
        "к дневной статистике школьника. Без советов, без оценок, только наблюдения.\n\n"
        f"Дата: {stats['date']}\n"
        f"Всего учтено: {stats['total']} мин\n"
        f"По категориям:\n{_format_by_category(stats['by_category'])}"
    )
    try:
        client = _deepseek_client()
        response = await client.chat.completions.create(
            model="deepseek-chat",
            messages=[{"role": "user", "content": prompt}],
            max_tokens=300,
            temperature=0.7,
        )
        return response.choices[0].message.content.strip()
    except Exception as e:
        log.warning("DeepSeek daily summary failed: %s", e)
        return _fallback_daily(stats)


async def _ai_weekly_summary(stats: dict) -> str:
    top_str = "\n".join(f"  • {n}: {m} мин" for n, m in stats["top"])
    prompt = (
        "Ты помощник по учёту времени. Напиши короткий недельный отчёт (1 абзац + 3 наблюдения "
        "+ 1–2 мягкие идеи) для школьника. Тон спокойный, без морализаторства.\n\n"
        f"Период: {stats['week_start']} — {stats['week_end']}\n"
        f"Всего учтено: {stats['total']} мин\n"
        f"Топ категорий:\n{top_str}"
    )
    try:
        client = _deepseek_client()
        response = await client.chat.completions.create(
            model="deepseek-chat",
            messages=[{"role": "user", "content": prompt}],
            max_tokens=500,
            temperature=0.7,
        )
        return response.choices[0].message.content.strip()
    except Exception as e:
        log.warning("DeepSeek weekly summary failed: %s", e)
        return _fallback_weekly(stats)


def _fallback_daily(stats: dict) -> str:
    total = stats["total"]
    h, m = divmod(total, 60)
    time_str = f"{h}ч {m}мин" if h else f"{m}мин"
    return f"Сегодня учтено {time_str} активности."


def _fallback_weekly(stats: dict) -> str:
    total = stats["total"]
    h, m = divmod(total, 60)
    time_str = f"{h}ч {m}мин" if h else f"{m}мин"
    return f"За неделю учтено {time_str} активности."


async def send_evening_reports(bot: Bot) -> None:
    async with AsyncSessionFactory() as session:
        result = await session.execute(
            select(User, UserSettings)
            .join(UserSettings, UserSettings.user_id == User.id)
            .where(
                UserSettings.evening_report_enabled == True,
                User.status == "active",
            )
        )
        users = result.all()

    for user, user_settings in users:
        try:
            async with AsyncSessionFactory() as session:
                stats = await get_today_stats(session, user.id)

            if not stats["by_category"]:
                continue  # nothing tracked today

            summary = await _ai_daily_summary(stats)
            cats_str = _format_by_category(stats["by_category"])
            total = stats["total"]
            h, m = divmod(total, 60)
            time_str = f"{h}ч {m}мин" if h else f"{m}мин"

            text = (
                f"🌙 <b>Итог дня</b>\n\n"
                f"{cats_str}\n\n"
                f"Всего: <b>{time_str}</b>\n\n"
                f"{summary}"
            )
            await bot.send_message(user.telegram_user_id, text, parse_mode="HTML")
        except Exception as e:
            log.error("Evening report failed for user %d: %s", user.telegram_user_id, e)


async def send_weekly_reports(bot: Bot) -> None:
    async with AsyncSessionFactory() as session:
        result = await session.execute(
            select(User, UserSettings)
            .join(UserSettings, UserSettings.user_id == User.id)
            .where(
                UserSettings.weekly_report_enabled == True,
                User.status == "active",
            )
        )
        users = result.all()

    for user, user_settings in users:
        try:
            async with AsyncSessionFactory() as session:
                stats = await get_week_stats(session, user.id)

            if not stats["by_category"]:
                continue

            summary = await _ai_weekly_summary(stats)
            top_str = _format_by_category(dict(stats["top"]))
            total = stats["total"]
            h, m = divmod(total, 60)
            time_str = f"{h}ч {m}мин" if h else f"{m}мин"

            text = (
                f"📅 <b>Итог недели</b> "
                f"({stats['week_start']} — {stats['week_end']})\n\n"
                f"Топ категорий:\n{top_str}\n\n"
                f"Всего: <b>{time_str}</b>\n\n"
                f"{summary}"
            )

            # Save summary to WeeklyAggregate
            async with AsyncSessionFactory() as session:
                async with session.begin():
                    from sqlalchemy import select as sel
                    res = await session.execute(
                        sel(WeeklyAggregate).where(
                            WeeklyAggregate.user_id == user.id,
                            WeeklyAggregate.week_start_date == stats["week_start"],
                        )
                    )
                    wagg = res.scalar_one_or_none()
                    if wagg:
                        wagg.summary_text = summary
                        wagg.total_minutes = stats["total"]
                    else:
                        session.add(WeeklyAggregate(
                            user_id=user.id,
                            week_start_date=stats["week_start"],
                            total_minutes=stats["total"],
                            metrics_json={"by_category": stats["by_category"]},
                            summary_text=summary,
                        ))

            await bot.send_message(user.telegram_user_id, text, parse_mode="HTML")
        except Exception as e:
            log.error("Weekly report failed for user %d: %s", user.telegram_user_id, e)
