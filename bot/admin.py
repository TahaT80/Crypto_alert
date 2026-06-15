"""پنل ادمین: مدیریت درخواست‌های خرید، آمار، لیست کاربران."""
from __future__ import annotations

import logging
import secrets
import time
from typing import Any, Dict, List, Optional

from telegram import Bot, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.error import BadRequest

from .config import ADMIN_IDS, PLANS, logger
from .storage import (
    load_pending_requests,
    load_subscriptions,
    save_pending_requests,
)
from .subscriptions import Subscription, is_admin, upgrade_plan

logger = logging.getLogger("bot")


def _md_escape(text: str) -> str:
    return text.replace("\\", "\\\\").replace("_", "\\_").replace("*", "\\*").replace("`", "\\`").replace("[", "\\[")


def _gen_request_id() -> str:
    return f"R{int(time.time())}{secrets.token_hex(2).upper()}"


# ============================================================
# درخواست‌های خرید
# ============================================================
async def create_pending_request(chat_id: int, plan_code: str) -> Optional[str]:
    """اگر درخواست pending برای این کاربر هست، همان را برمی‌گرداند.
    در غیر این صورت درخواست جدید می‌سازد.
    """
    if plan_code not in PLANS or PLANS[plan_code].price_toman == 0:
        return None
    data = await load_pending_requests()
    for rid, req in data.items():
        if req.get("user_id") == chat_id and req.get("status") == "pending":
            return rid
    new_id = _gen_request_id()
    data[new_id] = {
        "user_id": chat_id,
        "plan_code": plan_code,
        "status": "pending",
        "created_at": time.time(),
    }
    await save_pending_requests(data)
    return new_id


async def get_pending_for_user(chat_id: int) -> Optional[Dict[str, Any]]:
    data = await load_pending_requests()
    for rid, req in data.items():
        if req.get("user_id") == chat_id and req.get("status") == "pending":
            return {"id": rid, **req}
    return None


async def list_pending() -> List[Dict[str, Any]]:
    data = await load_pending_requests()
    return [
        {"id": rid, **req}
        for rid, req in data.items()
        if req.get("status") == "pending"
    ]


async def resolve_request(req_id: str, status: str, admin_id: int) -> Optional[Dict[str, Any]]:
    """تغییر وضعیت درخواست به approved/rejected. اگر قبلاً پردازش شده، None."""
    data = await load_pending_requests()
    req = data.get(req_id)
    if not req or req.get("status") != "pending":
        return None
    req["status"] = status
    req["resolved_at"] = time.time()
    req["admin_id"] = admin_id
    await save_pending_requests(data)
    return req


# ============================================================
# نوتیفیکیشن
# ============================================================
async def _format_user(bot: Bot, chat_id: int) -> str:
    try:
        chat = await bot.get_chat(chat_id)
        name = (chat.first_name or "").strip()
        if chat.last_name:
            name = (name + " " + chat.last_name).strip()
        username = f"@{chat.username}" if chat.username else ""
        safe_name = _md_escape(name or "—")
        safe_username = _md_escape(username)
        return f"👤 {safe_name} {safe_username} (`{chat_id}`)"
    except Exception:
        return f"👤 کاربر `{chat_id}`"


async def notify_admins_new_request(
    bot: Bot, req_id: str, chat_id: int, plan_code: str
) -> None:
    plan = PLANS.get(plan_code)
    if not plan:
        return
    user_line = await _format_user(bot, chat_id)
    text = (
        "📩 *درخواست خرید جدید*\n\n"
        f"🆔 شناسه: `{_md_escape(req_id)}`\n"
        f"{user_line}\n"
        f"💎 پلن: {plan.badge} *{plan.name_fa}*\n"
        f"💵 مبلغ: *{plan.price_text}*\n"
        f"🕐 مدت: {plan.duration_text}\n\n"
        f"⏳ منتظر تایید/رد شما..."
    )
    kb = InlineKeyboardMarkup([
        [
            InlineKeyboardButton("✅ تایید و فعال‌سازی", callback_data=f"APPROVE:{req_id}"),
            InlineKeyboardButton("❌ رد درخواست", callback_data=f"REJECT:{req_id}"),
        ],
        [
            InlineKeyboardButton("👤 اطلاعات کاربر", callback_data=f"UINFO:{chat_id}"),
        ],
    ])
    for admin_id in ADMIN_IDS:
        try:
            await bot.send_message(
                chat_id=admin_id, text=text, reply_markup=kb,
                parse_mode="Markdown",
            )
        except BadRequest as exc:
            logger.warning("Failed to notify admin %s: %s", admin_id, exc)
        except Exception as exc:
            logger.exception("Failed to notify admin %s: %s", admin_id, exc)


async def notify_user_request_result(
    bot: Bot, chat_id: int, approved: bool, plan_code: str
) -> None:
    plan = PLANS.get(plan_code)
    name = plan.name_fa if plan else plan_code
    badge = plan.badge if plan else ("✅" if approved else "❌")
    if approved:
        text = (
            f"{badge} *پلن {name} شما فعال شد!*\n\n"
            "🎉 از همین الان می‌تونید از امکانات پلن استفاده کنید.\n"
            "برای مشاهده پلن: /plan"
        )
    else:
        text = (
            f"{badge} *درخواست شما رد شد*\n\n"
            f"💎 پلن درخواستی: {name}\n\n"
            "برای اطلاعات بیشتر با ادمین تماس بگیرید."
        )
    try:
        await bot.send_message(chat_id=chat_id, text=text, parse_mode="Markdown")
    except Exception as exc:
        logger.warning("Failed to notify user %s: %s", chat_id, exc)


# ============================================================
# UI پنل ادمین
# ============================================================
def admin_main_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("📩 درخواست‌های خرید", callback_data="AREQ:0")],
        [
            InlineKeyboardButton("📊 آمار", callback_data="ASTATS"),
            InlineKeyboardButton("👥 لیست کاربران", callback_data="AUSERS:0"),
        ],
        [InlineKeyboardButton("🔍 جستجوی کاربر", callback_data="ASEARCH")],
        [InlineKeyboardButton("↩️ بستن", callback_data="EXITADMIN")],
    ])


async def _compute_stats() -> Dict[str, int]:
    subs_data = await load_subscriptions()
    stats = {"FREE": 0, "PRO": 0, "VIP": 0, "EXPIRED": 0, "TOTAL": 0}
    for cid, raw in subs_data.items():
        code = raw.get("plan", "FREE")
        if code not in ("FREE", "PRO", "VIP"):
            code = "FREE"
        if raw.get("expires_at"):
            try:
                sub = Subscription.from_dict(int(cid), raw)
                if not sub.is_active:
                    stats["EXPIRED"] += 1
                    continue
            except Exception:
                pass
        stats[code] += 1
    stats["TOTAL"] = sum(v for k, v in stats.items() if k in ("FREE", "PRO", "VIP", "EXPIRED"))
    return stats


async def render_admin_menu(bot: Bot, chat_id: int, edit_message=None) -> None:
    pending = await list_pending()
    stats = await _compute_stats()
    text = (
        "💼 *پنل ادمین*\n\n"
        "📊 *آمار کاربران:*\n"
        f"  🆓 FREE: {stats['FREE']}\n"
        f"  ⭐ PRO: {stats['PRO']}\n"
        f"  💎 VIP: {stats['VIP']}\n"
        f"  ⚠️ منقضی: {stats['EXPIRED']}\n"
        f"  👥 مجموع: {stats['TOTAL']}\n\n"
        f"📩 درخواست‌های در انتظار: *{len(pending)}*\n"
    )
    kb = admin_main_keyboard()
    if edit_message:
        try:
            await edit_message.edit_text(text, reply_markup=kb, parse_mode="Markdown")
            return
        except Exception as exc:
            if "not modified" in str(exc).lower():
                return
    try:
        await bot.send_message(
            chat_id=chat_id, text=text, reply_markup=kb, parse_mode="Markdown"
        )
    except Exception:
        pass


async def render_pending_list(bot: Bot, chat_id: int, page: int = 0, edit_message=None, per_page: int = 5) -> None:
    pending = await list_pending()
    pending.sort(key=lambda r: r.get("created_at", 0), reverse=True)
    if not pending:
        text = "📭 هیچ درخواست در انتظاری نیست."
        kb = InlineKeyboardMarkup([
            [InlineKeyboardButton("↩️ پنل ادمین", callback_data="ADMENU")]
        ])
        if edit_message:
            try:
                await edit_message.edit_text(text, reply_markup=kb, parse_mode="Markdown")
                return
            except Exception:
                pass
        await bot.send_message(chat_id=chat_id, text=text, reply_markup=kb, parse_mode="Markdown")
        return

    total = len(pending)
    start = page * per_page
    end = start + per_page
    page_items = pending[start:end]
    lines = [f"📩 *درخواست‌های خرید* — صفحه {page + 1}/{(total - 1) // per_page + 1}\n"]
    rows: List[List[InlineKeyboardButton]] = []
    for req in page_items:
        rid = req["id"]
        uid = req["user_id"]
        plan = PLANS.get(req["plan_code"])
        badge = plan.badge if plan else "?"
        name = plan.name_fa if plan else req["plan_code"]
        lines.append(
            f"• `{_md_escape(rid)}` — {badge} {name} — `{uid}`"
        )
        rows.append([
            InlineKeyboardButton(f"✅ {_md_escape(rid)[:14]}", callback_data=f"APPROVE:{rid}"),
            InlineKeyboardButton(f"❌ {_md_escape(rid)[:14]}", callback_data=f"REJECT:{rid}"),
        ])
    # pagination
    nav: List[InlineKeyboardButton] = []
    if page > 0:
        nav.append(InlineKeyboardButton("◀️ قبلی", callback_data=f"AREQ:{page - 1}"))
    if end < total:
        nav.append(InlineKeyboardButton("بعدی ▶️", callback_data=f"AREQ:{page + 1}"))
    if nav:
        rows.append(nav)
    rows.append([InlineKeyboardButton("↩️ پنل ادمین", callback_data="ADMENU")])
    text = "\n".join(lines)
    kb = InlineKeyboardMarkup(rows)
    if edit_message:
        try:
            await edit_message.edit_text(text, reply_markup=kb, parse_mode="Markdown")
            return
        except Exception as exc:
            if "not modified" in str(exc).lower():
                return
    await bot.send_message(chat_id=chat_id, text=text, reply_markup=kb, parse_mode="Markdown")


async def render_user_list(bot: Bot, chat_id: int, page: int = 0, edit_message=None, per_page: int = 10) -> None:
    subs_data = await load_subscriptions()
    items: List[Subscription] = []
    for cid, raw in subs_data.items():
        try:
            items.append(Subscription.from_dict(int(cid), raw))
        except Exception:
            continue
    items.sort(key=lambda s: s.joined_at or "", reverse=True)
    total = len(items)
    if total == 0:
        text = "📭 هیچ کاربری ثبت‌نام نکرده."
        kb = InlineKeyboardMarkup([[InlineKeyboardButton("↩️ پنل ادمین", callback_data="ADMENU")]])
        if edit_message:
            try:
                await edit_message.edit_text(text, reply_markup=kb)
                return
            except Exception:
                pass
        await bot.send_message(chat_id=chat_id, text=text, reply_markup=kb)
        return

    start = page * per_page
    end = start + per_page
    page_items = items[start:end]
    lines = [f"👥 *کاربران* — صفحه {page + 1}/{(total - 1) // per_page + 1}\n"]
    for sub in page_items:
        days = sub.days_left
        days_text = f" ({days}d)" if days is not None and days >= 0 else ""
        status = "✅" if sub.is_active else "⚠️"
        lines.append(
            f"{status} {sub.plan.badge} `{sub.chat_id}`{days_text}"
        )
    nav: List[InlineKeyboardButton] = []
    if page > 0:
        nav.append(InlineKeyboardButton("◀️", callback_data=f"AUSERS:{page - 1}"))
    if end < total:
        nav.append(InlineKeyboardButton("▶️", callback_data=f"AUSERS:{page + 1}"))
    rows: List[List[InlineKeyboardButton]] = []
    if nav:
        rows.append(nav)
    rows.append([InlineKeyboardButton("↩️ پنل ادمین", callback_data="ADMENU")])
    text = "\n".join(lines)
    kb = InlineKeyboardMarkup(rows)
    if edit_message:
        try:
            await edit_message.edit_text(text, reply_markup=kb, parse_mode="Markdown")
            return
        except Exception as exc:
            if "not modified" in str(exc).lower():
                return
    await bot.send_message(chat_id=chat_id, text=text, reply_markup=kb, parse_mode="Markdown")


async def render_user_info(bot: Bot, target_id: int) -> str:
    from .storage import get_chart_usage_today, load_alerts

    sub = await _get_sub(target_id)
    alerts = await load_alerts()
    user_alerts = alerts.get(str(target_id), [])
    charts_used, charts_limit = await get_chart_usage_today(target_id)
    user_line = await _format_user(bot, target_id)
    expiry = sub.expires_at or "بدون انقضا"
    days = sub.days_left
    days_text = f" ({days} روز مانده)" if days is not None and days >= 0 else ""
    active = "✅ فعال" if sub.is_active else "⚠️ منقضی"
    return (
        f"{user_line}\n\n"
        f"💎 پلن: {sub.plan.badge} {sub.plan.name_fa} — {active}\n"
        f"📅 انقضا: {expiry}{days_text}\n"
        f"🔔 هشدار فعال: {len(user_alerts)}/{sub.plan.max_alerts_text}\n"
        f"📊 نمودار امروز: {charts_used}/"
        f"{'∞' if charts_limit == -1 else charts_limit}"
    )


async def _get_sub(target_id: int) -> Subscription:
    from .subscriptions import get_subscription
    return await get_subscription(target_id)


async def search_user_prompt(bot: Bot, chat_id: int) -> None:
    await bot.send_message(
        chat_id=chat_id,
        text=(
            "🔍 *جستجوی کاربر*\n\n"
            "آیدی عددی کاربر را بفرست تا اطلاعات پلنش نمایش داده بشه.\n\n"
            "مثال: `123456789`\n\n"
            "برای لغو: /cancel"
        ),
        parse_mode="Markdown",
    )


# ============================================================
# اکشن‌های ادمین
# ============================================================
async def approve_request(bot: Bot, req_id: str, admin_id: int) -> Dict[str, Any]:
    """تایید درخواست. برمی‌گرداند: {ok, message, user_id, plan_code}."""
    req = await resolve_request(req_id, "approved", admin_id)
    if not req:
        return {"ok": False, "message": "❌ درخواست یافت نشد یا قبلاً پردازش شده."}
    user_id = req["user_id"]
    plan_code = req["plan_code"]
    sub = await upgrade_plan(user_id, plan_code)
    await notify_user_request_result(bot, user_id, True, plan_code)
    return {
        "ok": True,
        "message": f"✅ درخواست تایید و پلن {sub.plan.badge} {sub.plan.name_fa} فعال شد.",
        "user_id": user_id,
        "plan_code": plan_code,
    }


async def reject_request(bot: Bot, req_id: str, admin_id: int) -> Dict[str, Any]:
    req = await resolve_request(req_id, "rejected", admin_id)
    if not req:
        return {"ok": False, "message": "❌ درخواست یافت نشد یا قبلاً پردازش شده."}
    user_id = req["user_id"]
    plan_code = req["plan_code"]
    await notify_user_request_result(bot, user_id, False, plan_code)
    return {
        "ok": True,
        "message": f"❌ درخواست رد شد.",
        "user_id": user_id,
        "plan_code": plan_code,
    }


__all__ = [
    "is_admin",
    "create_pending_request",
    "get_pending_for_user",
    "list_pending",
    "resolve_request",
    "notify_admins_new_request",
    "notify_user_request_result",
    "admin_main_keyboard",
    "render_admin_menu",
    "render_pending_list",
    "render_user_list",
    "render_user_info",
    "search_user_prompt",
    "approve_request",
    "reject_request",
]
