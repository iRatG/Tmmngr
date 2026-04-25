"""TimeMirror — FastAPI app with aiogram webhook and APScheduler."""
import logging

from aiogram import Bot, Dispatcher
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.types import Update
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

from config import settings
from bot.handlers import onboarding, activity, reminder, status, user_settings
from scheduler.jobs import setup_jobs

logging.basicConfig(
    level=getattr(logging, settings.log_level.upper(), logging.INFO),
    format="%(asctime)s %(levelname)s %(name)s: %(message)s",
)
log = logging.getLogger(__name__)

# ── Bot + Dispatcher ──────────────────────────────────────────────────────────

bot = Bot(token=settings.telegram_bot_token)
dp = Dispatcher(storage=MemoryStorage())

dp.include_router(onboarding.router)
dp.include_router(activity.router)
dp.include_router(reminder.router)
dp.include_router(status.router)
dp.include_router(user_settings.router)

# ── FastAPI app ───────────────────────────────────────────────────────────────

app = FastAPI(title="TimeMirror")


@app.on_event("startup")
async def on_startup() -> None:
    scheduler = setup_jobs(bot)
    scheduler.start()
    log.info("Scheduler started with %d jobs", len(scheduler.get_jobs()))

    webhook_url = settings.telegram_webhook_url
    if webhook_url:
        await bot.set_webhook(
            url=webhook_url,
            drop_pending_updates=True,
        )
        log.info("Webhook set: %s", webhook_url)
    else:
        log.warning("TELEGRAM_WEBHOOK_URL not set — webhook not registered")


@app.on_event("shutdown")
async def on_shutdown() -> None:
    from scheduler.jobs import get_scheduler
    scheduler = get_scheduler()
    if scheduler.running:
        scheduler.shutdown(wait=False)
    await bot.session.close()
    log.info("Shutdown complete")


@app.get("/health")
async def health() -> dict:
    return {"status": "ok"}


@app.post("/webhook")
async def webhook(request: Request) -> JSONResponse:
    data = await request.json()
    update = Update.model_validate(data)
    await dp.feed_update(bot=bot, update=update)
    return JSONResponse({"ok": True})
