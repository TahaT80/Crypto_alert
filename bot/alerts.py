"""مدیریت هشدارهای قیمت: CRUD + تسک پس‌زمینه بررسی."""
from __future__ import annotations

import asyncio
import logging
import re
from enum import Enum
from typing import Any, Dict, List, Optional

from telegram import Bot, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.constants import ChatAction

from .config import (
    ALERTS_PER_PAGE,
    MAX_ALERTS_PER_USER,
    PRICE_CHECK_INTERVAL,
)
from .prices import get_price_info, get_prices_batch
from .storage import load_alerts, save_alerts
from .ui import alert_list_keyboard
from .utils import fmt_change, fmt_price

logger = logging.getLogger("bot")


class Direction(str, Enum):
    UP = "U"
    DOWN = "D"

    @classmethod
    def from_string(cls, s: str) -> "Direction":
        if not isinstance(s, str):
            raise ValueError("Invalid direction")
        s = s.strip().upper()
        if s in ("U", "UP", "بالا", "صعودی"):
            return cls.UP
        if s in ("D", "DOWN", "پایین", "نزولی"):
            return cls.DOWN
        raise ValueError("Direction must be U/D")


def _normalize_dir(d: str) -> Optional[str]:
    s = d.strip().lower()
    if s in ("u", "up", "بالا", "صعودی", "↗"):
        return "U"
    if s in ("d", "down", "پایین", "نزولی", "↘"):
        return "D"
    return None


def parse_alert_input(text: str, current_price: float | None = None):
    """پارس کردن ورودی هشدار.

    اگر فقط عدد فرستاده شود و current_price موجود باشد:
      - target > current → U (بالا)
      - target < current → D (پایین)
      - target == current → D (پیش‌فرض)

    اگر direction صریح بفرستد (U/D/بالا/پایین)، همان استفاده می‌شود.
    """
    s = text.strip()
    if not s:
        return (None, "❌ متن خالی")
    m = re.match(r"^([0-9]*\.?[0-9]+)\s*([a-zA-Z\u0600-\u06FF]{1,8})$", s)
    if m:
        try:
            target = float(m.group(1))
        except ValueError:
            return (None, "❌ قیمت هدف باید عدد باشد")
        d = _normalize_dir(m.group(2))
        if not d:
            return (None, "❌ جهت باید U (بالا) یا D (پایین) باشد")
        return ((target, d), None)
    parts = s.split()
    if len(parts) == 1:
        try:
            target = float(parts[0])
        except ValueError:
            return (None, "❌ قیمت هدف باید عدد باشد")
        if current_price is not None and current_price > 0:
            direction = "U" if target > current_price else "D"
        else:
            direction = "U"
        return ((target, direction), None)
    if len(parts) == 2:
        try:
            target = float(parts[0])
        except ValueError:
            return (None, "❌ قیمت هدف باید عدد باشد")
        d = _normalize_dir(parts[1])
        if not d:
            return (None, "❌ جهت باید U (بالا) یا D (پایین) باشد")
        return ((target, d), None)
    return (None, "❌ فرمت اشتباه. مثال: 120000 U")


async def create_alert(
    chat_id: str, symbol: str, target: float, direction: str
) -> Dict[str, Any]:
    """ایجاد هشدار با رعایت محدودیت پلن کاربر."""
    from .subscriptions import get_subscription

    alerts = await load_alerts()
    user_alerts = alerts.setdefault(chat_id, [])

    # ابتدا محدودیت سخت سراسری (ایمنی)
    if len(user_alerts) >= MAX_ALERTS_PER_USER:
        raise ValueError(
            f"❌ حداکثر {MAX_ALERTS_PER_USER} هشدار مجاز است."
        )

    # سپس محدودیت پلن (اگر منقضی شده باشد، FREE اعمال می‌شود)
    try:
        sub = await get_subscription(int(chat_id))
        limit = sub.effective_plan.max_alerts
        if limit != -1 and len(user_alerts) >= limit:
            plan_name = f"{sub.effective_plan.badge} {sub.effective_plan.name_fa}"
            raise ValueError(
                f"❌ پلن {plan_name} فقط {limit} هشدار همزمان مجاز دارد.\n"
                f"💎 برای ارتقا: /plan"
            )
    except ValueError:
        raise
    except Exception:
        pass  # در صورت خطا، فقط محدودیت سخت اعمال شود

    new_id = max((a.get("id", 0) for a in user_alerts), default=0) + 1
    user_alerts.append({
        "id": new_id,
        "symbol": symbol,
        "target": target,
        "goal": direction,
    })
    await save_alerts(alerts)
    return user_alerts[-1]


async def delete_alert(chat_id: str, alert_id: int) -> int:
    alerts = await load_alerts()
    if chat_id not in alerts or not alerts[chat_id]:
        return 0
    before = len(alerts[chat_id])
    alerts[chat_id] = [a for a in alerts[chat_id] if a.get("id") != alert_id]
    removed = before - len(alerts[chat_id])
    if not alerts[chat_id]:
        del alerts[chat_id]
    if removed:
        await save_alerts(alerts)
    return removed


async def delete_all_alerts(chat_id: str) -> int:
    alerts = await load_alerts()
    n = len(alerts.get(chat_id, []))
    if chat_id in alerts:
        del alerts[chat_id]
        await save_alerts(alerts)
    return n


async def render_alert_list(
    chat_id: str, bot: Bot, page: int = 0, edit_message=None
) -> None:
    alerts = await load_alerts()
    user_alerts = alerts.get(chat_id, [])
    if not user_alerts:
        text = "📭 هیچ هشداری ثبت نکرده‌اید.\n\nاز منوی پایین ➕ افزودن هشدار را بزنید."
        kb = InlineKeyboardMarkup([[
            InlineKeyboardButton("➕ افزودن هشدار", callback_data="ADDHELP:")
        ]])
        if edit_message:
            try:
                await edit_message.edit_text(text, reply_markup=kb)
            except Exception:
                pass
        else:
            await bot.send_message(chat_id=int(chat_id), text=text, reply_markup=kb)
        return

    symbols = list({a["symbol"] for a in user_alerts})
    price_cache: Dict[str, Optional[float]] = {}
    if symbols:
        batch = await get_prices_batch(symbols)
        for s in symbols:
            info = batch.get(s)
            price_cache[s] = info["price"] if info and "price" in info else None

    total = len(user_alerts)
    start = page * ALERTS_PER_PAGE
    end = start + ALERTS_PER_PAGE
    page_alerts = user_alerts[start:end]
    lines = [
        f"📋 هشدارهای شما — صفحه {page + 1} از {(total - 1) // ALERTS_PER_PAGE + 1}\n"
    ]
    for a in page_alerts:
        aid = a["id"]
        sym = a["symbol"]
        tgt = a["target"]
        arrow = "⬆️" if a["goal"] == "U" else "⬇️"
        cur = price_cache.get(sym)
        if cur is not None:
            diff = tgt - cur
            pct = (diff / cur * 100) if cur else 0
            line = (
                f"#{aid}  {sym}\n"
                f"     هدف: {fmt_price(tgt)} {arrow}   "
                f"فعلی: {fmt_price(cur)} ({pct:+.2f}%)"
            )
        else:
            line = f"#{aid}  {sym}\n     هدف: {fmt_price(tgt)} {arrow}   فعلی: —"
        lines.append(line)
    text = "\n\n".join(lines)
    kb = InlineKeyboardMarkup(
        [
            *[
                [
                    InlineKeyboardButton(
                        f"🗑 #{a['id']}", callback_data=f"DEL:{a['id']}"
                    ),
                    InlineKeyboardButton(
                        f"📊 {a['symbol']}", callback_data=f"CHART:{a['symbol']}:1h"
                    ),
                ]
                for a in page_alerts
            ],
            *alert_list_keyboard(total, page).inline_keyboard,
        ]
    )
    if edit_message:
        try:
            await edit_message.edit_text(text, reply_markup=kb)
        except Exception as exc:
            if "not modified" not in str(exc).lower():
                logger.warning("edit_text failed: %s", exc)
    else:
        await bot.send_message(chat_id=int(chat_id), text=text, reply_markup=kb)


# ============================================================
# تسک پس‌زمینه: بررسی هشدارها
# ============================================================
async def check_alerts_loop(bot: Bot) -> None:
    """هر PRICE_CHECK_INTERVAL ثانیه قیمت‌ها را چک می‌کند و هشدار فعال‌شده را می‌فرستد."""
    logger.info("check_alerts started")
    while True:
        try:
            alerts = await load_alerts()
            if not alerts:
                await asyncio.sleep(PRICE_CHECK_INTERVAL)
                continue

            all_symbols = {
                a.get("symbol")
                for user_alerts in alerts.values()
                for a in user_alerts
                if a.get("symbol")
            }
            if not all_symbols:
                await asyncio.sleep(PRICE_CHECK_INTERVAL)
                continue

            price_cache = await get_prices_batch(list(all_symbols))

            changed = False
            for chat_id, user_alerts in list(alerts.items()):
                if not user_alerts:
                    continue
                remaining: List[Dict[str, Any]] = []
                for alert in list(user_alerts):
                    try:
                        symbol = alert.get("symbol")
                        if not symbol:
                            continue
                        info = price_cache.get(symbol)
                        if not info or "price" not in info:
                            remaining.append(alert)
                            continue
                        price = float(info["price"])
                        change = info.get("change")
                        target = float(alert["target"])
                        try:
                            direction = Direction.from_string(alert.get("goal", "U"))
                        except ValueError:
                            remaining.append(alert)
                            continue
                        triggered = (
                            (direction == Direction.UP and price >= target)
                            or (direction == Direction.DOWN and price <= target)
                        )
                        if triggered:
                            changed = True
                            arrow = "⬆️" if direction == Direction.UP else "⬇️"
                            lines = [
                                "🎯 هشدار فعال شد!",
                                "",
                                f"💎 ارز: {symbol}",
                                f"💰 قیمت فعلی: {fmt_price(price)} {arrow}",
                                f"🎯 هدف: {fmt_price(target)}",
                            ]
                            if change is not None:
                                lines.append(fmt_change(change))
                            msg = "\n".join(lines)
                            kb = InlineKeyboardMarkup([[
                                InlineKeyboardButton(
                                    "📊 چارت", callback_data=f"CHART:{symbol}:1h"
                                ),
                                InlineKeyboardButton(
                                    "📋 هشدارها", callback_data="LIST:0"
                                ),
                            ]])
                            try:
                                await bot.send_message(
                                    chat_id=int(chat_id),
                                    text=msg,
                                    reply_markup=kb,
                                )
                            except Exception:
                                logger.exception("Failed to send alert to %s", chat_id)
                        else:
                            remaining.append(alert)
                    except Exception:
                        logger.exception(
                            "alert processing error: %s | %s", alert, chat_id
                        )
                        remaining.append(alert)
                if removed_count := (len(user_alerts) - len(remaining)):
                    alerts[chat_id] = remaining
                    changed = True

            if changed:
                await save_alerts(alerts)
        except asyncio.CancelledError:
            logger.info("check_alerts cancelled, exiting")
            raise
        except Exception:
            logger.exception("[check_alerts] fatal error; sleeping 5s")
            await asyncio.sleep(5)
            continue
        await asyncio.sleep(PRICE_CHECK_INTERVAL)
