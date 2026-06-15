"""Startup و error handler — جدا از main.py برای تمیزی."""
from __future__ import annotations

import asyncio
import logging
from zoneinfo import ZoneInfoNotFoundError
from zoneinfo import ZoneInfo
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger
from telegram import Update
from telegram.error import Conflict, NetworkError, TimedOut
from telegram.ext import ContextTypes

from .alerts import check_alerts_loop
from .config import (
    TIMEZONE,
)
from .subscriptions import demote_all_expired

logger = logging.getLogger("bot")


async def _demote_expired_job() -> None:
    n = await demote_all_expired()
    if n:
        logger.info("Auto-demoted %d expired subscriptions to FREE", n)


async def on_startup(application) -> None:
    """راه‌اندازی تسک‌های پس‌زمینه پس از اینیت."""
    bot = application.bot

    # تنزل پلن‌های منقضی در استارتاپ
    try:
        await _demote_expired_job()
    except Exception:
        logger.exception("Initial demote failed (non-fatal)")

    # تسک چک قیمت — با auto-restart در صورت crash
    async def _alerts_runner() -> None:
        await check_alerts_loop(bot)

    def _on_alerts_done(t: asyncio.Task) -> None:
        if t.cancelled():
            return
        exc = t.exception()
        if exc and not isinstance(exc, asyncio.CancelledError):
            logger.exception("check_alerts crashed: %s; restarting in 5s", exc)
            try:
                loop = asyncio.get_running_loop()
                loop.call_later(5, lambda: asyncio.create_task(_alerts_runner()))
            except RuntimeError:
                pass

    application.bot_data["alerts_task"] = asyncio.create_task(_alerts_runner())
    application.bot_data["alerts_task"].add_done_callback(_on_alerts_done)

    # scheduler برای تسک‌های دوره‌ای
    try:
        tz = ZoneInfo(TIMEZONE)
    except ZoneInfoNotFoundError:
        tz = ZoneInfo("UTC")
    scheduler = AsyncIOScheduler(timezone=str(tz))
    # تسک روزانه: تنزل پلن‌های منقضی (هر شب 00:05)
    scheduler.add_job(
        _demote_expired_job,
        CronTrigger(hour=0, minute=5, timezone=tz),
        id="demote_expired",
        replace_existing=True,
        misfire_grace_time=3600,
        coalesce=True,
    )
    scheduler.start()
    application.bot_data["scheduler"] = scheduler
    logger.info(
        "✅ Scheduler started — demote expired daily at 00:05 (%s)",
        TIMEZONE,
    )


async def on_shutdown(application) -> None:
    """پاکسازی منابع در هنگام خروج."""
    try:
        scheduler = application.bot_data.get("scheduler")
        if scheduler:
            scheduler.shutdown(wait=False)
    except Exception:
        pass
    try:
        task = application.bot_data.get("alerts_task")
        if task and not task.done():
            task.cancel()
    except Exception:
        pass
    try:
        from .http_client import close_client
        await close_client()
    except Exception:
        pass


async def error_handler(update: object, context: ContextTypes.DEFAULT_TYPE) -> None:
    err = context.error
    if isinstance(err, Conflict):
        logger.error(
            "⚠️  نمونه دیگری از بات در حال اجراست (Conflict). "
            "نمونه قبلی را ببندید."
        )
        return
    if isinstance(err, TimedOut):
        logger.warning("⏱️  Timeout در ارتباط با تلگرام — تلاش مجدد...")
        return
    if isinstance(err, NetworkError):
        logger.warning("🌐 خطای شبکه در ارتباط با تلگرام: %s", err)
        return

    logger.exception("خطای غیرمنتظره: %s", err)
    if isinstance(update, Update) and update.effective_chat:
        try:
            await context.bot.send_message(
                chat_id=update.effective_chat.id,
                text="❌ خطایی رخ داد. لطفاً دوباره تلاش کنید.",
            )
        except Exception:
            pass
