"""مدیریت اشتراک‌ها و پلن‌ها: FREE / PRO / VIP.

ساختار فایل subscriptions.json:
{
  "<chat_id>": {
    "plan": "FREE" | "PRO" | "VIP",
    "joined_at": "2026-06-06 12:00:00",
    "expires_at": null | "2026-07-06 12:00:00"
  },
  ...
}
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Dict, Optional

from .config import (
    ADMIN_CONTACT,
    ADMIN_IDS,
    DEFAULT_PLAN,
    PLANS,
    Plan,
    TEHRAN_TZ,
)
from .storage import (
    load_subscribers,
    load_subscriptions,
    save_subscribers,
    save_subscriptions,
)


def is_admin(user_id: int) -> bool:
    return user_id in ADMIN_IDS


@dataclass
class Subscription:
    chat_id: int
    plan_code: str
    joined_at: str
    expires_at: Optional[str] = None
    previous_plan: Optional[str] = None
    demoted_at: Optional[str] = None

    @property
    def plan(self) -> Plan:
        return PLANS.get(self.plan_code, PLANS[DEFAULT_PLAN])

    @property
    def effective_plan(self) -> Plan:
        if not self.is_active:
            return PLANS[DEFAULT_PLAN]
        return self.plan

    @property
    def is_active(self) -> bool:
        if not self.expires_at:
            return True
        try:
            exp = datetime.fromisoformat(self.expires_at)
            if exp.tzinfo is None:
                exp = exp.replace(tzinfo=TEHRAN_TZ)
            return exp > datetime.now(TEHRAN_TZ)
        except Exception:
            return True

    @property
    def days_left(self) -> Optional[int]:
        if not self.expires_at:
            return None
        try:
            exp = datetime.fromisoformat(self.expires_at)
            if exp.tzinfo is None:
                exp = exp.replace(tzinfo=TEHRAN_TZ)
            delta = exp - datetime.now(TEHRAN_TZ)
            return max(0, int(delta.total_seconds() // 86400))
        except Exception:
            return None

    @property
    def was_demoted(self) -> bool:
        return (
            self.previous_plan is not None
            and self.previous_plan != self.plan_code
            and self.plan_code == DEFAULT_PLAN
        )

    def to_dict(self) -> Dict:
        return {
            "plan": self.plan_code,
            "joined_at": self.joined_at,
            "expires_at": self.expires_at,
            "previous_plan": self.previous_plan,
            "demoted_at": self.demoted_at,
        }

    @staticmethod
    def from_dict(chat_id: int, data: Dict) -> "Subscription":
        return Subscription(
            chat_id=chat_id,
            plan_code=data.get("plan", DEFAULT_PLAN),
            joined_at=data.get("joined_at", ""),
            expires_at=data.get("expires_at"),
            previous_plan=data.get("previous_plan"),
            demoted_at=data.get("demoted_at"),
        )


async def get_subscription(chat_id: int) -> Subscription:
    data = await load_subscriptions()
    raw = data.get(str(chat_id))
    if not raw:
        return Subscription(
            chat_id=chat_id,
            plan_code=DEFAULT_PLAN,
            joined_at=datetime.now(TEHRAN_TZ).strftime("%Y-%m-%d %H:%M:%S"),
        )
    return Subscription.from_dict(chat_id, raw)


async def set_subscription(sub: Subscription) -> None:
    data = await load_subscriptions()
    data[str(sub.chat_id)] = sub.to_dict()
    await save_subscriptions(data)
    subs = await load_subscribers()
    subs.add(sub.chat_id)
    await save_subscribers(subs)


async def upgrade_plan(chat_id: int, plan_code: str, duration_days: Optional[int] = None) -> Subscription:
    plan = PLANS.get(plan_code, PLANS[DEFAULT_PLAN])
    sub = await get_subscription(chat_id)
    sub.plan_code = plan.code
    if not sub.joined_at:
        sub.joined_at = datetime.now(TEHRAN_TZ).strftime("%Y-%m-%d %H:%M:%S")
    days = duration_days if duration_days is not None else plan.duration_days
    if plan.price_toman == 0 or days == 0:
        sub.expires_at = None
    else:
        exp = datetime.now(TEHRAN_TZ) + timedelta(days=days)
        sub.expires_at = exp.replace(microsecond=0).isoformat()
    sub.previous_plan = None
    sub.demoted_at = None
    await set_subscription(sub)
    return sub


async def remove_subscription(chat_id: int) -> None:
    data = await load_subscriptions()
    if str(chat_id) in data:
        del data[str(chat_id)]
        await save_subscriptions(data)
    subs = await load_subscribers()
    subs.discard(chat_id)
    await save_subscribers(subs)


# ── Auto-demotion ──────────────────────────────────────────
async def check_and_demote_if_expired(chat_id: int) -> bool:
    data = await load_subscriptions()
    raw = data.get(str(chat_id))
    if not raw:
        return False
    expires_at = raw.get("expires_at")
    if not expires_at:
        return False
    try:
        exp = datetime.fromisoformat(expires_at)
        if exp.tzinfo is None:
            exp = exp.replace(tzinfo=TEHRAN_TZ)
    except Exception:
        return False
    if exp > datetime.now(TEHRAN_TZ):
        return False
    current_plan = raw.get("plan", DEFAULT_PLAN)
    if current_plan == DEFAULT_PLAN:
        return False
    raw["previous_plan"] = current_plan
    raw["plan"] = DEFAULT_PLAN
    raw["demoted_at"] = datetime.now(TEHRAN_TZ).isoformat()
    raw["expires_at"] = None
    await save_subscriptions(data)
    return True


async def demote_all_expired() -> int:
    data = await load_subscriptions()
    changed = 0
    now = datetime.now(TEHRAN_TZ)
    for cid, raw in list(data.items()):
        expires_at = raw.get("expires_at")
        if not expires_at:
            continue
        try:
            exp = datetime.fromisoformat(expires_at)
            if exp.tzinfo is None:
                exp = exp.replace(tzinfo=TEHRAN_TZ)
        except Exception:
            continue
        if exp > now:
            continue
        current_plan = raw.get("plan", DEFAULT_PLAN)
        if current_plan == DEFAULT_PLAN:
            continue
        raw["previous_plan"] = current_plan
        raw["plan"] = DEFAULT_PLAN
        raw["demoted_at"] = now.isoformat()
        raw["expires_at"] = None
        changed += 1
    if changed:
        await save_subscriptions(data)
    return changed


# ── Plan rendering ─────────────────────────────────────────
def _expiry_text(sub: Subscription) -> str:
    if not sub.expires_at:
        if sub.plan.price_toman == 0:
            return "♾️ بدون انقضا"
        return "⏳ در انتظار فعال‌سازی توسط ادمین"
    days = sub.days_left
    if days is None:
        return f"📅 انقضا: {sub.expires_at[:10]}"
    if days == 0:
        return "⚠️ امروز آخرین روز!"
    if days <= 3:
        return f"⚠️ {days} روز مانده ({sub.expires_at[:10]})"
    return f"📅 {days} روز مانده ({sub.expires_at[:10]})"


def render_plan_card(plan: Plan, current: bool = False, sub: Optional[Subscription] = None) -> str:
    badge = "👈 پلن فعلی شما" if current else ""
    features = "\n".join(plan.features)
    extra = ""
    if current and sub is not None:
        extra = f"\n⏰ {_expiry_text(sub)}"
    return (
        f"{plan.badge} *پلن {plan.name_fa}* {badge}\n"
        f"💵 قیمت: {plan.price_text}\n"
        f"🕐 مدت: {plan.duration_text}\n"
        f"🔔 هشدار همزمان: {plan.max_alerts_text}\n"
        f"📈 نمودار روزانه: {plan.max_charts_text}"
        f"{extra}\n\n"
        f"✨ امکانات:\n{features}\n"
    )


def _md_escape(text: str) -> str:
    return text.replace("\\", "\\\\").replace("_", "\\_").replace("*", "\\*").replace("`", "\\`").replace("[", "\\[")


def render_all_plans(current_code: str, current_sub: Optional[Subscription] = None) -> str:
    contact_user = ADMIN_CONTACT.lstrip("@")
    contact_link = f"https://t.me/{contact_user}"
    contact_display = _md_escape(f"@{contact_user}")
    parts = [
        "💎 *انتخاب پلن اشتراک*\n",
        "با فعال‌سازی پلن، هشدارهای قیمت و نمودارهای بیشتری دریافت کنید.\n",
    ]
    if current_sub is not None and current_sub.was_demoted:
        prev_plan = PLANS.get(current_sub.previous_plan or "")
        if prev_plan:
            parts.append(
                f"⚠️ *پلن قبلی شما ({prev_plan.badge} {prev_plan.name_fa}) منقضی شد.* "
                f"برای ادامه دسترسی، تمدید کنید.\n"
            )
    parts.extend([
        "💳 *روش فعال‌سازی پلن‌های PRO / VIP:*",
        f"  • پیام به [{contact_display}]({contact_link})",
        "  • پلن دلخواه + رسید پرداخت را بفرستید",
        "  • فعال‌سازی کمتر از ۱ ساعت\n",
    ])
    for code in ("FREE", "PRO", "VIP"):
        plan = PLANS[code]
        is_cur = (code == current_code)
        parts.append(render_plan_card(plan, current=is_cur, sub=current_sub if is_cur else None))
        parts.append("")
    return "\n".join(parts).rstrip()


def plan_inline_keyboard(current_code: str) -> "list":
    from telegram import InlineKeyboardButton, InlineKeyboardMarkup
    rows = []
    for code in ("FREE", "PRO", "VIP"):
        plan = PLANS[code]
        label = f"{plan.badge} {plan.name_fa}"
        label += " — فعال‌سازی" if plan.price_toman == 0 else " — 💳 خرید"
        if code == current_code:
            label = f"✅ {label} (فعلی)"
        rows.append([InlineKeyboardButton(label, callback_data=f"PLAN:{code}")])
    return InlineKeyboardMarkup(rows)
