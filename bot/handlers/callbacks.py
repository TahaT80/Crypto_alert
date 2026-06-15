"""پاسخ به دکمه‌های شیشه‌ای (callback)."""
from __future__ import annotations

import logging

from telegram import (
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    Update,
)
from telegram.ext import ContextTypes

from ..admin import (
    approve_request,
    is_admin,
    notify_admins_new_request,
    create_pending_request,
    reject_request,
    render_admin_menu,
    render_pending_list,
    render_user_info,
    render_user_list,
    search_user_prompt,
)
from ..alerts import delete_alert, delete_all_alerts, render_alert_list
from ..handlers.commands import _send_chart_to_chat
from ..subscriptions import (
    ADMIN_CONTACT,
    PLANS,
    _md_escape,
    check_and_demote_if_expired,
    get_subscription,
    plan_inline_keyboard,
    render_all_plans,
    set_subscription,
)
from ..ui import main_keyboard

logger = logging.getLogger("bot")


async def callback_handler(
    update: Update, context: ContextTypes.DEFAULT_TYPE
) -> None:
    query = update.callback_query
    if not query:
        return
    try:
        await query.answer()
    except Exception:
        pass
    data = query.data or ""
    chat_id = str(query.message.chat_id) if query.message else ""
    user_id = update.effective_user.id if update.effective_user else 0

    # ----- حذف یک هشدار -----
    if data.startswith("DEL:"):
        try:
            aid = int(data.split(":", 1)[1])
        except ValueError:
            return
        removed = await delete_alert(chat_id, aid)
        if removed:
            try:
                await context.bot.answer_callback_query(
                    query.id, text=f"✅ هشدار #{aid} حذف شد", show_alert=False
                )
            except Exception:
                pass
            await render_alert_list(
                chat_id, context.bot, page=0, edit_message=query.message
            )
        else:
            try:
                await context.bot.answer_callback_query(
                    query.id, text="❌ یافت نشد", show_alert=True
                )
            except Exception:
                pass
        return

    # ----- حذف همه -----
    if data == "DELALL":
        n = await delete_all_alerts(chat_id)
        try:
            await context.bot.answer_callback_query(
                query.id, text=f"✅ {n} هشدار حذف شد", show_alert=True
            )
        except Exception:
            pass
        await render_alert_list(chat_id, context.bot, page=0, edit_message=query.message)
        return

    # ----- صفحه‌بندی -----
    if data.startswith("LIST:"):
        try:
            page = int(data.split(":", 1)[1])
        except ValueError:
            page = 0
        await render_alert_list(chat_id, context.bot, page=page, edit_message=query.message)
        return

    # ----- چارت -----
    if data.startswith("CHART:"):
        if not query.message:
            return
        parts = data.split(":")
        symbol = parts[1] if len(parts) > 1 else "BTCUSDT"
        tf = parts[2] if len(parts) > 2 else "4h"
        await _send_chart_to_chat(context.bot, int(query.message.chat_id), symbol, tf)
        return

    # ----- شروع ساخت هشدار از قیمت -----
    if data.startswith("ADDALERT:"):
        sym = data.split(":", 1)[1].upper()
        try:
            await query.answer()
        except Exception:
            pass
        context.user_data["expecting_alert_symbol"] = sym
        try:
            await query.message.reply_text(
                f"🎯 ساخت هشدار برای {sym}\n\n"
                f" قیمت هدف رو بفرسته:\n"
                f"برای لغو /cancel یا ↩️ بازگشت بزن.",
                reply_markup=main_keyboard(),
                parse_mode="Markdown",
            )
        except Exception:
            pass
        return

    if data.startswith("ADDHELP"):
        parts = data.split(":", 1)
        sym = parts[1] if len(parts) > 1 and parts[1] else ""
        extra = f" (برای {sym})" if sym else ""
        try:
            await query.message.reply_text(
                f"➕ افزودن هشدار{extra}:\n\n"
                "راحت‌ترین راه: روی «🎯 تنظیم هشدار قیمت» زیر قیمت هر ارز بزن.\n"
                "دستی: /add SYMBOL TARGET U|D\n"
                "مثال: /add BTCUSDT 120000 U",
                reply_markup=main_keyboard(),
            )
        except Exception:
            pass
        return

    # ----- انتخاب پلن -----
    if data.startswith("PLAN:"):
        plan_code = data.split(":", 1)[1]
        if plan_code not in PLANS:
            return
        # اول پلن منقضی شده را به FREE تنزل بده (data به‌روز شود)
        await check_and_demote_if_expired(int(chat_id))
        plan = PLANS[plan_code]
        sub = await get_subscription(int(chat_id))

        if plan.price_toman == 0:
            # FREE: فعال‌سازی مستقیم بدون پرداخت
            sub.plan_code = plan_code
            await set_subscription(sub)
            msg = (
                f"{plan.badge} پلن {plan.name_fa} فعال شد ✅\n\n"
                "از همین الان می‌تونی از امکانات پلن استفاده کنی."
            )
            toast = f"✅ {plan.name_fa}"
        else:
            # PRO/VIP: نمایش اطلاعات پرداخت + ثبت درخواست + نوتیفی ادمین
            contact_user = ADMIN_CONTACT.lstrip("@")
            contact_link = f"https://t.me/{contact_user}"
            contact_display = _md_escape(f"@{contact_user}")
            msg = (
                f"{plan.badge} *درخواست پلن {plan.name_fa}*\n\n"
                f"💵 مبلغ: *{plan.price_text}*\n"
                f"🕐 مدت: {plan.duration_text}\n\n"
                "*💳 مراحل فعال‌سازی:*\n"
                f"  1️⃣ مبلغ *{plan.price_text}* را به [{contact_display}]({contact_link}) واریز کن\n"
                f"  2️⃣ رسید پرداخت + کلمه «{plan.code}» را به ادمین بفرست\n"
                f"  3️⃣ ادمین پلن شما را فعال می‌کند (کمتر از ۱ ساعت)\n\n"
                f"⏳ درخواست شما ثبت شد و به ادمین ارسال شد. "
                f"پس از تایید، خودکار فعال می‌شود.\n\n"
                f"💡 پلن فعلی شما ({sub.plan.badge} {sub.plan.name_fa}) تا آن زمان فعال است."
            )
            toast = f"💳 {plan.name_fa}"
            # ساخت درخواست + ارسال به ادمین‌ها
            try:
                req_id = await create_pending_request(int(chat_id), plan_code)
                if req_id:
                    await notify_admins_new_request(
                        context.bot, req_id, int(chat_id), plan_code
                    )
            except Exception as exc:
                logger.exception("Failed to create/notify pending request: %s", exc)

        try:
            await context.bot.answer_callback_query(query.id, text=toast, show_alert=False)
        except Exception:
            pass
        # ویرایش پیام فعلی با کارت پلن‌ها
        try:
            await query.message.edit_text(
                render_all_plans(sub.plan.code),
                reply_markup=plan_inline_keyboard(sub.plan.code),
                parse_mode="Markdown",
            )
        except Exception:
            pass
        # ارسال پیام راهنما
        try:
            await query.message.reply_text(msg, parse_mode="Markdown", disable_web_page_preview=True)
        except Exception:
            try:
                await query.message.reply_text(msg, disable_web_page_preview=True)
            except Exception:
                pass
        return

    # ============================================================
    # پنل ادمین — فقط برای ADMIN_IDS
    # ============================================================
    if not is_admin(user_id):
        # برای امنیت، callbackهای ادمینی نباید توسط غیر ادمین اجرا شوند
        if data.startswith(("ADMENU", "AREQ", "ASTATS", "AUSERS", "ASEARCH",
                            "APPROVE", "REJECT", "UINFO", "EXITADMIN",
                            "AGRANT", "AREVOKE")):
            try:
                await context.bot.answer_callback_query(
                    query.id, text="⛔ دسترسی ندارید", show_alert=True
                )
            except Exception:
                pass
            return

    if data == "ADMENU":
        await render_admin_menu(context.bot, int(chat_id), edit_message=query.message)
        return

    if data == "EXITADMIN":
        try:
            await query.message.delete()
        except Exception:
            try:
                await query.message.edit_text("بسته شد ✅")
            except Exception:
                pass
        return

    if data.startswith("AREQ:"):
        try:
            page = int(data.split(":", 1)[1])
        except ValueError:
            page = 0
        await render_pending_list(context.bot, int(chat_id), page=page, edit_message=query.message)
        return

    if data == "ASTATS":
        await render_admin_menu(context.bot, int(chat_id), edit_message=query.message)
        return

    if data.startswith("AUSERS:"):
        try:
            page = int(data.split(":", 1)[1])
        except ValueError:
            page = 0
        await render_user_list(context.bot, int(chat_id), page=page, edit_message=query.message)
        return

    if data == "ASEARCH":
        context.user_data["awaiting_user_id"] = True
        await search_user_prompt(context.bot, int(chat_id))
        try:
            await context.bot.answer_callback_query(query.id)
        except Exception:
            pass
        return

    if data.startswith("UINFO:"):
        try:
            target_id = int(data.split(":", 1)[1])
        except ValueError:
            return
        text = await render_user_info(context.bot, target_id)
        kb = InlineKeyboardMarkup([
            [
                InlineKeyboardButton("➕ ارتقا پلن", callback_data=f"AGRANT:{target_id}"),
                InlineKeyboardButton("🚫 حذف اشتراک", callback_data=f"AREVOKE:{target_id}"),
            ],
            [InlineKeyboardButton("↩️ پنل ادمین", callback_data="ADMENU")],
        ])
        try:
            await context.bot.send_message(
                chat_id=int(chat_id), text=text, reply_markup=kb, parse_mode="Markdown"
            )
        except Exception:
            pass
        return

    if data.startswith("APPROVE:"):
        req_id = data.split(":", 1)[1]
        result = await approve_request(context.bot, req_id, user_id)
        try:
            await context.bot.answer_callback_query(
                query.id, text=result["message"][:200], show_alert=True
            )
        except Exception:
            pass
        try:
            await query.message.edit_text(
                f"{result['message']}\n\n"
                f"📋 درخواست: `{req_id}`\n"
                f"👤 کاربر: `{result.get('user_id', '?')}`\n"
                f"💎 پلن: `{result.get('plan_code', '?')}`",
                reply_markup=InlineKeyboardMarkup([
                    [InlineKeyboardButton("📩 درخواست‌های دیگر", callback_data="AREQ:0")],
                    [InlineKeyboardButton("↩️ پنل ادمین", callback_data="ADMENU")],
                ]),
                parse_mode="Markdown",
            )
        except Exception:
            pass
        return

    if data.startswith("REJECT:"):
        req_id = data.split(":", 1)[1]
        result = await reject_request(context.bot, req_id, user_id)
        try:
            await context.bot.answer_callback_query(
                query.id, text=result["message"][:200], show_alert=True
            )
        except Exception:
            pass
        try:
            await query.message.edit_text(
                f"{result['message']}\n\n"
                f"📋 درخواست: `{req_id}`\n"
                f"👤 کاربر: `{result.get('user_id', '?')}`\n"
                f"💎 پلن: `{result.get('plan_code', '?')}`",
                reply_markup=InlineKeyboardMarkup([
                    [InlineKeyboardButton("📩 درخواست‌های دیگر", callback_data="AREQ:0")],
                    [InlineKeyboardButton("↩️ پنل ادمین", callback_data="ADMENU")],
                ]),
                parse_mode="Markdown",
            )
        except Exception:
            pass
        return

    if data.startswith("AGRANT:"):
        # راهنما برای grant دستی
        try:
            target_id = int(data.split(":", 1)[1])
        except ValueError:
            return
        text = (
            f"➕ *ارتقای پلن کاربر `{target_id}`*\n\n"
            "دستور زیر را در همین چت بفرست:\n\n"
            f"`/grant {target_id} PRO 30`\n"
            f"`/grant {target_id} VIP 30`\n\n"
            "عدد آخر = روز (پیش‌فرض: ۳۰)"
        )
        kb = InlineKeyboardMarkup([
            [InlineKeyboardButton("↩️ پنل ادمین", callback_data="ADMENU")],
        ])
        try:
            await context.bot.send_message(
                chat_id=int(chat_id), text=text, reply_markup=kb, parse_mode="Markdown"
            )
        except Exception:
            pass
        return

    if data.startswith("AREVOKE:"):
        try:
            target_id = int(data.split(":", 1)[1])
        except ValueError:
            return
        text = (
            f"🚫 *حذف اشتراک کاربر `{target_id}`*\n\n"
            "دستور زیر را بفرست:\n\n"
            f"`/revoke {target_id}`"
        )
        kb = InlineKeyboardMarkup([
            [InlineKeyboardButton("↩️ پنل ادمین", callback_data="ADMENU")],
        ])
        try:
            await context.bot.send_message(
                chat_id=int(chat_id), text=text, reply_markup=kb, parse_mode="Markdown"
            )
        except Exception:
            pass
        return


