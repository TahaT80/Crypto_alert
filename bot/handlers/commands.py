"""دستورات اصلی: /start, /help, /add, /list, /delete, /p, /chart, /plan, /subscribe."""
from __future__ import annotations

import logging
import time

from telegram import (
    Bot,
    Update,
)
from telegram.constants import ChatAction
from telegram.ext import ContextTypes

from ..alerts import (
    Direction,
    create_alert,
    delete_alert,
    render_alert_list,
)
from ..config import CHART_API_KEY, SYMBOL_REGEX
from ..http_client import download_bytes
from ..prices import get_price_info
from ..subscriptions import (
    get_subscription,
    plan_inline_keyboard,
    render_all_plans,
    set_subscription,
    check_and_demote_if_expired,
)
from ..ui import main_keyboard, price_keyboard
from ..utils import fmt_change, fmt_price, fmt_volume

logger = logging.getLogger("bot")

HELP_TEXT = (
    "ℹ️ راهنمای ربات\n\n"
    "🔔 **هشدار قیمت:**\n"
    "  • /add SYMBOL TARGET [U|D]  (مثال: /add BTCUSDT 120000)\n"
    "  • اگه U/D نفرستی، خودش از قیمت فعلی تشخیص میده:\n"
    "    بالاتر → U ⬆️   /   پایین‌تر → D ⬇️\n"
    "  • /list   - لیست هشدارها\n"
    "  • /delete ID - حذف هشدار\n\n"
    "💲 **قیمت و چارت:**\n"
    "  • /p SYMBOL  (مثال: /p BTC یا /p BTCUSDT)\n"
    "  • /chart SYMBOL [TF]  (مثال: /chart ETH 4h)\n"
    "  • تعداد نمودار روزانه بستگی به پلن دارد\n\n"
    "💎 **اشتراک و پلن‌ها:**\n"
    "  • /plan یا 💎 پلن‌ها — مقایسه FREE / PRO / VIP\n"
    "  • /subscribe — فعال‌سازی\n"
    "  • /unsubscribe — لغو اشتراک\n\n"
    "🔹 نکات: فقط «BTC» بفرست، خودش BTCUSDT رو امتحان می‌کنه.\n"
    "  برای Perpetual: BTCUSDT.P\n"
    "  برای دامیننس: BTC.D، TOTAL\n"
)


# ============================================================
# /start, /help, /cancel
# ============================================================
async def start_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user = update.effective_user
    name = user.first_name if user and user.first_name else "دوست عزیز"
    sub = await get_subscription(update.effective_chat.id)
    # هر کاربری که /start می‌زند، ثبت و به لیست subscribers اضافه می‌شود
    await set_subscription(sub)
    text = (
        f"سلام {name} 👋\n\n"
        "به ربات «Crypto Alert» خوش اومدی 🚀\n\n"
        "این ربات:\n"
        "🎯 هشدار قیمت می‌ذاره (اسپات + فیوچرز)\n"
        "💲 قیمت لحظه‌ای + چارت تکنیکال میده\n\n"
        f"💎 پلن فعلی شما: {sub.plan.badge} {sub.plan.name_fa}\n\n"
        "👇 از منوی پایین یکی رو انتخاب کن، یا /help رو بزن."
    )
    await update.message.reply_text(text, reply_markup=main_keyboard())


async def help_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await update.message.reply_text(HELP_TEXT, reply_markup=main_keyboard())


async def cancel_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    context.user_data.clear()
    await update.message.reply_text("عملیات لغو شد ✅", reply_markup=main_keyboard())


# ============================================================
# /add — افزودن هشدار
# ============================================================
async def add_alert_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    chat_id = str(update.effective_chat.id)
    args = context.args
    if len(args) not in (2, 3):
        await update.message.reply_text(
            "❌ فرمت اشتباه است.\n"
            "فرمت صحیح:\n"
            "  /add SYMBOL TARGET U|D   (صریح)\n"
            "  /add SYMBOL TARGET        (جهت خودکار)\n\n"
            "مثال‌ها:\n"
            "  /add BTCUSDT 120000 U\n"
            "  /add ETHUSDT 3000 D\n"
            "  /add BTC.D 55 U\n"
            "  /add BTCUSDT 120000      ← بالاتر از قیمت فعلی → U\n"
            "  /add ETHUSDT 2000        ← پایین‌تر از قیمت فعلی → D"
        )
        return
    symbol_raw = args[0]
    target_str = args[1]
    direction_raw = args[2] if len(args) == 3 else None
    symbol = symbol_raw.upper()
    await update.effective_chat.send_action(ChatAction.TYPING)
    info = await get_price_info(symbol)
    if not info:
        await update.message.reply_text(
            f"❌ نماد «{symbol}» پیدا نشد.\n"
            "نماد دقیق‌تری وارد کن (مثل BTCUSDT) یا از 💲 قیمت لحظه‌ای استفاده کن."
        )
        return
    try:
        target = float(target_str)
    except ValueError:
        await update.message.reply_text("❌ قیمت هدف باید عدد باشد.")
        return
    auto_detected = False
    if direction_raw is None:
        cur = info["price"]
        direction_value = "U" if target > cur else "D"
        auto_detected = target != cur
    else:
        try:
            direction = Direction.from_string(direction_raw)
            direction_value = direction.value
        except ValueError:
            await update.message.reply_text(
                "❌ جهت باید U (بالا) یا D (پایین) باشد."
            )
            return
    try:
        new = await create_alert(chat_id, info["symbol"], target, direction_value)
    except ValueError as exc:
        await update.message.reply_text(f"❌ {exc}")
        return
    cur = info["price"]
    diff = target - cur
    pct = (diff / cur * 100) if cur else 0
    arrow = "⬆️" if direction_value == "U" else "⬇️"
    dir_fa = "بالا" if direction_value == "U" else "پایین"

    text = (
        "✅ هشدار ثبت شد\n\n"
        f"🔖 شناسه: #{new['id']}\n"
        f"💎 ارز: {info['symbol']}\n"
        f"💰 قیمت فعلی: {fmt_price(cur)}\n"
        f"🎯 هدف: {fmt_price(target)} {arrow} ({dir_fa})\n"
        f"📏 فاصله تا هدف: {pct:+.2f}%"
    )
    await update.message.reply_text(text, reply_markup=main_keyboard())


# ============================================================
# /list, /delete
# ============================================================
async def list_alerts_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await render_alert_list(str(update.effective_chat.id), context.bot)


async def delete_alert_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    chat_id = str(update.effective_chat.id)
    args = context.args
    if not args or not args[0].isdigit():
        await update.message.reply_text("❌ فرمت: /delete ID\nمثال: /delete 1")
        return
    removed = await delete_alert(chat_id, int(args[0]))
    if removed:
        await update.message.reply_text(
            f"✅ هشدار #{args[0]} حذف شد.", reply_markup=main_keyboard()
        )
    else:
        await update.message.reply_text("❌ هشداری با آن شناسه یافت نشد.")


# ============================================================
# /p, /chart
# ============================================================
async def price_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not context.args:
        await update.message.reply_text("فرمت: /p SYMBOL\nمثال: /p BTC یا /p BTCUSDT")
        return
    await _send_price(update, context, context.args[0].upper())


async def _send_price(
    update_or_query, context: ContextTypes.DEFAULT_TYPE, symbol: str
) -> None:
    if hasattr(update_or_query, "effective_chat") and update_or_query.effective_chat:
        chat = update_or_query.effective_chat
    elif hasattr(update_or_query, "message") and update_or_query.message:
        chat = update_or_query.message.chat
    else:
        return
    try:
        await context.bot.send_chat_action(chat_id=chat.id, action=ChatAction.TYPING)
    except Exception:
        pass
    info = await get_price_info(symbol)
    if not info:
        msg = (
            f"❌ نماد «{symbol}» پیدا نشد.\n"
            "نماد صحیح را وارد کنید (مثل BTCUSDT، ETHUSDT، BTC.D)."
        )
        try:
            await context.bot.send_message(chat_id=chat.id, text=msg)
        except Exception:
            pass
        return
    cur = info["price"]
    ch = info.get("change", 0.0) or 0.0
    trend = "صعودی 🐂" if ch > 0 else ("نزولی 🐻" if ch < 0 else "خنثی ➖")
    strength = "قوی 💪" if abs(ch) > 3 else ("متوسط ✋" if abs(ch) > 1 else "ضعیف 🤏")
    text = (
        f"📊 اطلاعات {info['symbol']} ({info['market']})\n\n"
        f"💰 قیمت: {fmt_price(cur)}\n"
        f"{fmt_change(ch)}\n"
        f"🔺 بالای ۲۴h: {fmt_price(info.get('high', 0))}\n"
        f"🔻 پایین ۲۴h: {fmt_price(info.get('low', 0))}\n"
        f"📦 حجم معاملات: {fmt_volume(info.get('quote_volume', 0))}\n"
        f"📌 روند: {trend} - قدرت {strength}"
    )
    try:
        if hasattr(update_or_query, "message") and update_or_query.message:
            await update_or_query.message.reply_text(
                text, reply_markup=price_keyboard(info["symbol"])
            )
        else:
            await context.bot.send_message(
                chat_id=chat.id, text=text, reply_markup=price_keyboard(info["symbol"])
            )
    except Exception:
        logger.exception("send_price message failed")


async def chart_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not context.args:
        await update.message.reply_text(
            "فرمت: /chart SYMBOL [TF]\n"
            "TF اختیاری: 1m, 5m, 15m, 1h, 4h, 1d, 1w\n"
            "مثال: /chart BTCUSDT 4h"
        )
        return
    symbol = context.args[0].upper()
    tf = context.args[1] if len(context.args) > 1 else "4h"
    await _send_chart_to_chat(context.bot, update.effective_chat.id, symbol, tf)


async def _send_chart_to_chat(
    bot: Bot, chat_id: int, symbol: str, tf: str
) -> None:
    from ..storage import check_and_increment_chart

    # بررسی محدودیت نمودار روزانه پلن
    allowed, used, limit = await check_and_increment_chart(chat_id)
    if not allowed:
        limit_text = "∞" if limit == -1 else str(limit)
        await bot.send_message(
            chat_id=chat_id,
            text=(
                f"⚠️ سقف نمودار روزانه پلن شما ({used}/{limit_text}) پر شد.\n"
                f"💎 برای ارتقا: /plan"
            ),
        )
        return

    limit_text = "∞" if limit == -1 else f"{used}/{limit}"

    if not CHART_API_KEY:
        try:
            await bot.send_chat_action(chat_id=chat_id, action=ChatAction.TYPING)
        except Exception:
            pass
        info = await get_price_info(symbol)
        if not info:
            await bot.send_message(
                chat_id=chat_id,
                text=(
                    f"❌ نماد یافت نشد و کلید چارت هم تنظیم نیست.\n"
                    f"📊 نمودار امروز: {limit_text}"
                ),
            )
            return
        ch = info.get("change", 0.0) or 0.0
        text = (
            f"📊 {info['symbol']} ({tf})\n"
            f"💰 قیمت: {fmt_price(info['price'])}\n"
            f"{fmt_change(ch)}\n\n"
            f"📈 نمودار امروز: {limit_text}"
        )
        await bot.send_message(chat_id=chat_id, text=text)
        return
    try:
        await bot.send_chat_action(chat_id=chat_id, action=ChatAction.UPLOAD_PHOTO)
    except Exception:
        pass
    info = await get_price_info(symbol)
    if not info:
        await bot.send_message(chat_id=chat_id, text="❌ نماد برای چارت یافت نشد.")
        return
    chart_url = (
        "https://api.chart-img.com/v1/tradingview/advanced-chart"
        f"?symbol=BINANCE:{symbol}&interval={tf}"
        "&studies=BB&studies=RSI&studies=EMA:50&height=600&theme=dark"
        f"&key={CHART_API_KEY}&_t={int(time.time())}"
    )
    ch = info.get("change", 0.0) or 0.0
    trend = "صعودی 🐂" if ch > 0 else "نزولی 🐻"
    caption = (
        f"📊 {info['symbol']} — {tf}\n"
        f"💰 قیمت: {fmt_price(info['price'])}\n"
        f"{fmt_change(ch)} | روند: {trend}\n\n"
        f"📈 نمودار امروز: {limit_text}"
    )
    data = await download_bytes(chart_url)
    if not data:
        await bot.send_message(chat_id=chat_id, text="❌ خطا در دریافت چارت از سرور.")
        return
    try:
        await bot.send_photo(chat_id=chat_id, photo=data, caption=caption)
    except Exception as exc:
        logger.exception("send_photo failed: %s", exc)
        await bot.send_message(chat_id=chat_id, text=caption)


# ============================================================
# /plan, /subscribe, /unsubscribe
# ============================================================
async def plan_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    # اول پلن منقضی شده را به FREE تنزل بده (data را به‌روز کن)
    await check_and_demote_if_expired(update.effective_chat.id)
    sub = await get_subscription(update.effective_chat.id)
    text = render_all_plans(sub.plan.code, current_sub=sub)
    await update.message.reply_text(
        text, reply_markup=plan_inline_keyboard(sub.plan.code),
        parse_mode="Markdown",
    )


async def subscribe_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    chat_id = update.effective_chat.id
    sub = await get_subscription(chat_id)
    await set_subscription(sub)
    await update.message.reply_text(
        f"✅ شما عضو شدید (پلن {sub.plan.badge} {sub.plan.name_fa}).\n\n"
        f"💎 برای ارتقا به PRO/VIP: /plan"
    )


async def unsubscribe_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    chat_id = update.effective_chat.id
    sub = await get_subscription(chat_id)
    await update.message.reply_text(
        "🚫 اشتراک شما لغو شد.\n\n"
        "برای فعال‌سازی مجدد: /subscribe"
    )


# ============================================================
# دستورات ادمین — فقط برای ADMIN_IDS
# ============================================================
async def _reject_non_admin(update: Update) -> bool:
    """اگر کاربر ادمین نیست، پیام خطا می‌فرستد و True برمی‌گرداند."""
    from ..subscriptions import is_admin
    if not is_admin(update.effective_user.id):
        await update.message.reply_text("⛔ این دستور فقط برای ادمین است.")
        return True
    return False


async def grant_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """/grant <user_id> <PLAN> [days]
    مثال: /grant 123456 PRO 30"""
    from ..subscriptions import is_admin, upgrade_plan
    from ..config import PLANS

    if await _reject_non_admin(update):
        return
    args = context.args
    if len(args) < 2:
        await update.message.reply_text(
            "📌 فرمت:\n"
            "  /grant <user_id> <PLAN> [days]\n\n"
            "مثال‌ها:\n"
            "  /grant 123456789 PRO 30\n"
            "  /grant 123456789 VIP 90\n"
            "  /grant 123456789 FREE 0\n\n"
            f"پلن‌های موجود: {', '.join(PLANS.keys())}"
        )
        return
    try:
        target_id = int(args[0])
    except ValueError:
        await update.message.reply_text("❌ user_id باید عدد باشد.")
        return
    plan_code = args[1].upper()
    if plan_code not in PLANS:
        await update.message.reply_text(
            f"❌ پلن نامعتبر. موجود: {', '.join(PLANS.keys())}"
        )
        return
    days = None
    if len(args) >= 3:
        try:
            days = int(args[2])
            if days < 0:
                raise ValueError
        except ValueError:
            await update.message.reply_text("❌ days باید عدد مثبت باشد.")
            return
    sub = await upgrade_plan(target_id, plan_code, duration_days=days)
    plan = PLANS[plan_code]
    days_text = (
        f"{days} روز" if days else plan.duration_text
    )
    expiry_text = sub.expires_at[:10] if sub.expires_at else "بدون انقضا"
    await update.message.reply_text(
        f"✅ پلن برای کاربر `{target_id}` تنظیم شد:\n\n"
        f"💎 پلن: {plan.badge} {plan.name_fa}\n"
        f"🕐 مدت: {days_text}\n"
        f"📅 انقضا: {expiry_text}\n\n"
        f"🔔 هشدار مجاز: {plan.max_alerts_text}\n"
        f"📊 نمودار/روز: {plan.max_charts_text}",
        parse_mode="Markdown",
    )


async def revoke_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """/revoke <user_id> — حذف کامل اشتراک کاربر"""
    from ..subscriptions import remove_subscription

    if await _reject_non_admin(update):
        return
    if not context.args or not context.args[0].lstrip("-").isdigit():
        await update.message.reply_text("📌 فرمت: /revoke <user_id>")
        return
    target_id = int(context.args[0])
    await remove_subscription(target_id)
    await update.message.reply_text(f"🚫 اشتراک کاربر `{target_id}` حذف شد.")


async def userinfo_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """/userinfo <user_id> — نمایش اطلاعات پلن کاربر"""
    from ..subscriptions import get_subscription
    from ..storage import load_alerts, get_chart_usage_today

    if await _reject_non_admin(update):
        return
    if not context.args or not context.args[0].lstrip("-").isdigit():
        await update.message.reply_text("📌 فرمت: /userinfo <user_id>")
        return
    target_id = int(context.args[0])
    # به‌روزرسانی پلن منقضی قبل از نمایش
    await check_and_demote_if_expired(target_id)
    sub = await get_subscription(target_id)
    alerts = await load_alerts()
    user_alerts = alerts.get(str(target_id), [])
    charts_used, charts_limit = await get_chart_usage_today(target_id)
    expiry = sub.expires_at or "بدون انقضا"
    days = sub.days_left
    days_text = f" ({days} روز مانده)" if days is not None else ""
    await update.message.reply_text(
        f"👤 اطلاعات کاربر `{target_id}`:\n\n"
        f"💎 پلن: {sub.plan.badge} {sub.plan.name_fa}\n"
        f"📅 انقضا: {expiry}{days_text}\n"
        f"🔔 هشدار فعال: {len(user_alerts)}/{sub.plan.max_alerts_text}\n"
        f"📊 نمودار امروز: {charts_used}/"
        f"{'∞' if charts_limit == -1 else charts_limit}",
        parse_mode="Markdown",
    )


async def admin_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """/admin — پنل ادمین برای مدیریت درخواست‌ها و کاربران."""
    from ..admin import is_admin, render_admin_menu

    if not is_admin(update.effective_user.id):
        await update.message.reply_text("⛔ این دستور فقط برای ادمین است.")
        return
    await render_admin_menu(context.bot, update.effective_chat.id)


async def plans_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """/plans — نمایش پلن‌ها برای ادمین با آمار"""
    from ..subscriptions import is_admin
    from ..config import PLANS
    from ..storage import load_subscriptions

    await check_and_demote_if_expired(update.effective_chat.id)
    sub = await get_subscription(update.effective_chat.id)
    text = render_all_plans(sub.plan.code, current_sub=sub)
    if is_admin(update.effective_user.id):
        # اضافه کردن آمار
        data = await load_subscriptions()
        stats = {"FREE": 0, "PRO": 0, "VIP": 0, "EXPIRED": 0}
        for raw in data.values():
            code = raw.get("plan", "FREE")
            if code not in stats:
                code = "FREE"
            if raw.get("expires_at"):
                try:
                    s = Subscription.from_dict(0, raw)
                    if not s.is_active:
                        stats["EXPIRED"] += 1
                        continue
                except Exception:
                    pass
            stats[code] += 1
        text += (
            "\n\n📊 *آمار ادمین:*\n"
            f"  🆓 FREE: {stats['FREE']}\n"
            f"  ⭐ PRO: {stats['PRO']}\n"
            f"  💎 VIP: {stats['VIP']}\n"
            f"  ⚠️ منقضی (در انتظار تنزل): {stats['EXPIRED']}\n"
            f"  مجموع: {sum(stats.values())}\n"
        )
    await update.message.reply_text(
        text, reply_markup=plan_inline_keyboard(sub.plan.code),
        parse_mode="Markdown",
    )

