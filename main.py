"""Telegram Bot: Crypto Alerts + Subscription Plans.

نقطه ورود اصلی.

اجرا: python main.py

ساختار:
    bot/
    ├── config.py          # تنظیمات، env، پلن‌ها
    ├── storage.py         # JSON I/O
    ├── http_client.py     # کلاینت HTTP
    ├── utils.py           # قالب‌بندی، زمان
    ├── prices.py          # قیمت بایننس + TradingView
    ├── ui.py              # کیبوردها
    ├── alerts.py          # CRUD هشدار + تسک پس‌زمینه
    ├── subscriptions.py   # پلن‌های FREE/PRO/VIP
    ├── update.py          # استارتاپ، scheduler، error handler
    ├── admin.py           # پنل ادمین
    └── handlers/          # هندلرهای تلگرام
        ├── commands.py
        ├── callbacks.py
        └── messages.py
"""
from __future__ import annotations

import json
import os
import traceback

from telegram.ext import (
    Application,
    ApplicationBuilder,
    CallbackQueryHandler,
    CommandHandler,
    MessageHandler,
    filters,
)

from bot.config import (
    HTTP_TIMEOUT_TELEGRAM_CONNECT,
    HTTP_TIMEOUT_TELEGRAM_READ,
    SUBSCRIBERS_FILE,
    TELEGRAM_TOKEN,
    logger,
)
from bot.handlers.callbacks import callback_handler
from bot.handlers.commands import (
    add_alert_cmd,
    admin_cmd,
    cancel_cmd,
    chart_cmd,
    delete_alert_cmd,
    grant_cmd,
    help_cmd,
    list_alerts_cmd,
    plan_cmd,
    plans_cmd,
    price_cmd,
    revoke_cmd,
    start_cmd,
    subscribe_cmd,
    unsubscribe_cmd,
    userinfo_cmd,
)
from bot.handlers.messages import handle_free_message
from bot.storage import ALERTS_FILE, SUBSCRIPTIONS_FILE
from bot.update import error_handler, on_shutdown, on_startup


# ============================================================
# ساخت Application
# ============================================================
def build_application() -> Application:
    app = (
        ApplicationBuilder()
        .token(TELEGRAM_TOKEN)
        .connect_timeout(HTTP_TIMEOUT_TELEGRAM_CONNECT)
        .read_timeout(HTTP_TIMEOUT_TELEGRAM_READ)
        .write_timeout(HTTP_TIMEOUT_TELEGRAM_READ)
        .build()
    )

    # --- Commands ---
    app.add_handler(CommandHandler("start", start_cmd))
    app.add_handler(CommandHandler("help", help_cmd))
    app.add_handler(CommandHandler("cancel", cancel_cmd))
    # Alerts
    app.add_handler(CommandHandler("add", add_alert_cmd))
    app.add_handler(CommandHandler("list", list_alerts_cmd))
    app.add_handler(CommandHandler("delete", delete_alert_cmd))
    # Prices
    app.add_handler(CommandHandler("p", price_cmd))
    app.add_handler(CommandHandler("chart", chart_cmd))
    # Subscription
    app.add_handler(CommandHandler("plan", plan_cmd))
    app.add_handler(CommandHandler("plans", plans_cmd))
    app.add_handler(CommandHandler("subscribe", subscribe_cmd))
    app.add_handler(CommandHandler("unsubscribe", unsubscribe_cmd))
    # Admin
    app.add_handler(CommandHandler("grant", grant_cmd))
    app.add_handler(CommandHandler("revoke", revoke_cmd))
    app.add_handler(CommandHandler("userinfo", userinfo_cmd))
    app.add_handler(CommandHandler("admin", admin_cmd))

    # --- Callback & Free text ---
    app.add_handler(CallbackQueryHandler(callback_handler))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_free_message))

    app.add_error_handler(error_handler)
    return app


def main() -> None:
    # ساخت فایل‌های اولیه در صورت نبود
    for path in (ALERTS_FILE, SUBSCRIBERS_FILE, SUBSCRIPTIONS_FILE):
        if not os.path.exists(path):
            try:
                with open(path, "w", encoding="utf-8") as f:
                    if path in (SUBSCRIBERS_FILE,):
                        json.dump([], f)
                    else:
                        json.dump({}, f)
            except Exception:
                logger.exception("Could not create %s", path)

    logger.info("🚀 BOT IS STARTING ...")
    try:
        app = build_application()
    except RuntimeError as exc:
        logger.critical("%s", exc)
        raise
    app.post_init = on_startup
    app.post_shutdown = on_shutdown
    app.run_polling(drop_pending_updates=True)


if __name__ == "__main__":
    try:
        main()
    except Exception:
        try:
            with open("crash_report.txt", "w", encoding="utf-8") as f:
                f.write("=== Exception Traceback ===\n")
                traceback.print_exc(file=f)
                f.write("\n=== end ===\n")
        except Exception:
            pass
        raise
