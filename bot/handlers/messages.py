"""پیام‌های آزاد (متن): دکمه‌های منو، ساخت هشدار inline، ورود نماد."""
from __future__ import annotations

import logging
from typing import Dict

from telegram import Update
from telegram.ext import ContextTypes

from ..alerts import (
    create_alert,
    parse_alert_input,
    render_alert_list,
)
from ..config import SYMBOL_REGEX
from ..handlers.commands import _send_price
from ..prices import get_price_info
from ..ui import back_keyboard, main_keyboard
from ..utils import fmt_price

logger = logging.getLogger("bot")

MENU_BUTTONS: Dict[str, str] = {
    "📋 هشدارهای من": "list",
    "💲 قیمت لحظه‌ای": "price",
    "➕ افزودن هشدار": "add",
    "🗑 حذف هشدار": "delete",
    "💎 پلن‌ها": "plan",
    "💼 پنل ادمین": "admin",
    "ℹ️ راهنما": "help",
    "↩️ بازگشت": "back",
}


async def handle_free_message(
    update: Update, context: ContextTypes.DEFAULT_TYPE
) -> None:
    if not update.message or not update.message.text:
        return
    text = update.message.text.strip()
    chat_id = str(update.effective_chat.id)

    # ---- در انتظار ورود قیمت/جهت برای ساخت هشدار ----
    pending_sym = context.user_data.get("expecting_alert_symbol")
    if pending_sym:
        context.user_data.pop("expecting_alert_symbol", None)
        # ابتدا قیمت فعلی را بگیر تا auto-detect جهت ممکن شود
        info = await get_price_info(pending_sym)
        cur_price = info["price"] if info else None
        result, err = parse_alert_input(text, current_price=cur_price)
        if err:
            context.user_data["expecting_alert_symbol"] = pending_sym
            await update.message.reply_text(
                f"{err}\n\nدوباره فقط قیمت و جهت رو بفرست.\n"
                f"مثال: `120000 U` یا `3000 D` یا فقط `120000`\n"
                f"(فقط عدد بفرست، خودش جهت رو از قیمت فعلی تشخیص میده)\n"
                f"برای لغو /cancel یا ↩️ بازگشت بزن.",
                reply_markup=back_keyboard(),
                parse_mode="Markdown",
            )
            return
        target, direction = result
        if not info:
            await update.message.reply_text(
                f"❌ نماد {pending_sym} یافت نشد.", reply_markup=main_keyboard()
            )
            return
        try:
            new = await create_alert(chat_id, info["symbol"], target, direction)
        except ValueError as exc:
            await update.message.reply_text(f"❌ {exc}", reply_markup=main_keyboard())
            return
        cur = info["price"]
        diff = target - cur
        pct = (diff / cur * 100) if cur else 0
        arrow = "⬆️" if direction == "U" else "⬇️"
        dir_fa = "بالا" if direction == "U" else "پایین"

        text_out = (
            "✅ هشدار ثبت شد\n\n"
            f"🔖 شناسه: #{new['id']}\n"
            f"💎 ارز: {info['symbol']}\n"
            f"💰 قیمت فعلی: {fmt_price(cur)}\n"
            f"🎯 هدف: {fmt_price(target)} {arrow} ({dir_fa})\n"
            f"📏 فاصله تا هدف: {pct:+.2f}%"
        )
        await update.message.reply_text(text_out, reply_markup=main_keyboard())
        return

    # ---- دکمه‌های منو ----
    action = MENU_BUTTONS.get(text)
    if action == "list":
        await render_alert_list(chat_id, context.bot)
        return
    if action == "price":
        await update.message.reply_text(
            "💲 نام ارز را بفرست:\n\n"
            "مثال: BTCUSDT، ETHUSDT.P، BTC.D",
            reply_markup=back_keyboard(),
        )
        return
    if action == "add":
        await update.message.reply_text(
            "➕ افزودن هشدار\n\n"
            "راحت‌ترین راه: 💲 قیمت یک ارز رو بگیر، بعد زیر پیام قیمت دکمه\n"
            "«🎯 تنظیم هشدار قیمت» رو بزن.\n\n"
            "🤖 فقط قیمت بفرست، جهت خودکار تشخیص داده میشه:\n"
            "  • بالاتر از قیمت فعلی → U ⬆️\n"
            "  • پایین‌تر از قیمت فعلی → D ⬇️\n\n"
            "دستی:\n"
            "  /add SYMBOL TARGET U|D\n"
            "  /add SYMBOL TARGET         (auto)\n\n"
            "مثال:\n"
            "  /add BTCUSDT 120000        ← اگه الان 100K باشه → U\n"
            "  /add ETHUSDT 2000          ← اگه الان 3000 باشه → D",
            reply_markup=main_keyboard(),
        )
        return
    if action == "delete":
        await render_alert_list(chat_id, context.bot)
        return
    if action == "plan":
        from ..handlers.commands import plan_cmd
        await plan_cmd(update, context)
        return
    if action == "help":
        from ..handlers.commands import help_cmd
        await help_cmd(update, context)
        return
    if action == "back":
        context.user_data.clear()
        await update.message.reply_text("بازگشتیم ✅", reply_markup=main_keyboard())
        return

    if action == "admin":
        from ..admin import is_admin, render_admin_menu
        if not is_admin(update.effective_user.id):
            await update.message.reply_text("⛔ دسترسی ندارید.")
            return
        await render_admin_menu(context.bot, update.effective_chat.id)
        return

    # ---- در انتظار ورود آیدی عددی برای جستجوی کاربر (ادمین) ----
    if context.user_data.get("awaiting_user_id"):
        context.user_data.pop("awaiting_user_id", None)
        from ..admin import is_admin, render_user_info
        if not is_admin(update.effective_user.id):
            await update.message.reply_text("⛔ دسترسی ندارید.", reply_markup=main_keyboard())
            return
        if not text.lstrip("-").isdigit():
            await update.message.reply_text("❌ لطفاً فقط عدد (chat_id) بفرست.", reply_markup=main_keyboard())
            return
        target_id = int(text)
        info = await render_user_info(context.bot, target_id)
        from telegram import InlineKeyboardButton, InlineKeyboardMarkup
        kb = InlineKeyboardMarkup([
            [
                InlineKeyboardButton("➕ ارتقا", callback_data=f"AGRANT:{target_id}"),
                InlineKeyboardButton("🚫 حذف", callback_data=f"AREVOKE:{target_id}"),
            ],
            [InlineKeyboardButton("↩️ پنل ادمین", callback_data="ADMENU")],
        ])
        await update.message.reply_text(info, reply_markup=kb, parse_mode="Markdown")
        return

    # ---- ورود مستقیم نماد (BTC, BTCUSDT, ...) ----
    if SYMBOL_REGEX.match(text):
        await _send_price(update, context, text.upper())
        return
