# -*- coding: utf-8 -*-
"""
Crypto Alert Bot — ربات تلگرام هشدار قیمت و اخبار ارزهای دیجیتال
ویژگی‌ها:
  • هشدار قیمت (بالا/پایین) روی اسپات و فیوچرز بایننس
  • چارت تکنیکال با اندیکاتور RSI (اختیاری)
  • لیست هشدار با دکمه‌های شیشه‌ای (حذف، چارت، بروزرسانی، حذف همه)
  • صفحه‌بندی، کش، قفل فایل، لاگ تمیز
  • پشتیبانی از نمادهای TV (BTC.D, TOTAL, TOTAL2, ...)
  • تشخیص خودکار نماد کوتاه (BTC → BTCUSDT)
  • قابلیت جدید: اخبار مهم بازار کریپتو (RSS چند منبع: crypto.news، Decrypt، Cointelegraph، ...)
"""

import asyncio
import json
import logging
import os
import re
import time
import traceback
from datetime import datetime, timedelta, timezone
from email.utils import parsedate_to_datetime
from enum import Enum
from typing import Any, Dict, List, Optional
from xml.etree import ElementTree as ET

from dotenv import load_dotenv

load_dotenv()

import httpx
from telegram import (
    Bot,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    ReplyKeyboardMarkup,
    Update,
)
from telegram.constants import ChatAction
from telegram.ext import (
    ApplicationBuilder,
    CallbackQueryHandler,
    CommandHandler,
    ContextTypes,
    MessageHandler,
    filters,
)

# ============================================================
# پیکربندی
# ============================================================
TELEGRAM_TOKEN = os.environ.get("TELEGRAM_TOKEN", "").strip()
CMC_API_KEY = os.environ.get("CMC_API_KEY", "").strip()
CHART_API_KEY = os.environ.get("CHART_API_KEY", "").strip()

if not TELEGRAM_TOKEN:
    raise RuntimeError(
        "❌ TELEGRAM_TOKEN تنظیم نشده است.\n"
        "   لطفاً فایل .env را بسازید و مقدار TELEGRAM_TOKEN را در آن قرار دهید.\n"
        "   نمونه در .env.example موجود است."
    )

ALERTS_FILE = "alerts.json"
NEWS_CACHE_TTL = 300
PRICE_CHECK_INTERVAL = 15
ALERTS_PER_PAGE = 8
NEWS_PER_PAGE = 5

TV_MAP: Dict[str, str] = {
    "BTC.D": "CRYPTOCAP:BTC.D",
    "ETH.D": "CRYPTOCAP:ETH.D",
    "USDT.D": "CRYPTOCAP:USDT.D",
    "TOTAL": "CRYPTOCAP:TOTAL",
    "TOTAL2": "CRYPTOCAP:TOTAL2",
    "TOTAL3": "CRYPTOCAP:TOTAL3",
    "TOTAL3ES": "CRYPTOCAP:TOTAL3ES",
    "OTHERS.D": "CRYPTOCAP:OTHERS.D",
}
COMMON_QUOTES = ["USDT", "FDUSD", "TUSD", "BUSD", "USDC", "BTC", "ETH"]
MAX_ALERTS_PER_USER = 50
SYMBOL_REGEX = re.compile(r"^[A-Za-z0-9.\-]{2,20}$")

# ============================================================
# لاگینگ (سکوت برای کتابخانه‌های پرسروصدا)
# ============================================================
logger = logging.getLogger("crypto_alert")
logger.setLevel(logging.INFO)
logger.propagate = False
if not logger.handlers:
    _fh = logging.FileHandler("bot.log", encoding="utf-8")
    _fh.setFormatter(logging.Formatter("%(asctime)s %(levelname)s: %(message)s"))
    _ch = logging.StreamHandler()
    _ch.setFormatter(logging.Formatter("%(asctime)s %(levelname)s: %(message)s"))
    logger.addHandler(_fh)
    logger.addHandler(_ch)

for _noisy in ("httpx", "aiohttp", "apscheduler"):
    logging.getLogger(_noisy).setLevel(logging.WARNING)

# منطقه زمانی تهران
try:
    from zoneinfo import ZoneInfo
    TEHRAN_TZ: Any = ZoneInfo("Asia/Tehran")
except Exception:
    TEHRAN_TZ = timezone(timedelta(hours=3, minutes=30))

# TradingView اختیاری (نیازی به نصب نیست)
try:
    from tradingview_scraper.symbols.stream import RealTimeData  # type: ignore
except Exception:
    RealTimeData = None  # type: ignore


# ============================================================
# Enum جهت
# ============================================================
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


# ============================================================
# IO فایل هشدارها (با قفل async)
# ============================================================
_file_lock = asyncio.Lock()


def _load_alerts_sync() -> Dict[str, Any]:
    if not os.path.exists(ALERTS_FILE):
        return {}
    try:
        with open(ALERTS_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)
            return data if isinstance(data, dict) else {}
    except (json.JSONDecodeError, OSError):
        logger.exception("Failed to load alerts file")
        return {}


def _save_alerts_sync(data: Dict[str, Any]) -> None:
    tmp = ALERTS_FILE + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    os.replace(tmp, ALERTS_FILE)


async def load_alerts() -> Dict[str, Any]:
    async with _file_lock:
        return await asyncio.to_thread(_load_alerts_sync)


async def save_alerts(data: Dict[str, Any]) -> None:
    async with _file_lock:
        await asyncio.to_thread(_save_alerts_sync, data)


# ============================================================
# HTTP utilities
# ============================================================
async def fetch_with_retry(
    url: str,
    retries: int = 3,
    delay: float = 1.2,
    timeout: float = 10.0,
) -> Optional[Any]:
    last_exc: Optional[Exception] = None
    for attempt in range(retries):
        try:
            async with httpx.AsyncClient(timeout=timeout) as client:
                resp = await client.get(url)
                if resp.status_code == 400:
                    return None
                if resp.status_code == 429 or resp.status_code >= 500:
                    last_exc = httpx.HTTPStatusError(
                        "retryable", request=resp.request, response=resp
                    )
                else:
                    resp.raise_for_status()
                    ct = resp.headers.get("content-type", "")
                    if "application/json" in ct:
                        return resp.json()
                    return resp.text
        except (httpx.HTTPError, asyncio.TimeoutError) as e:
            last_exc = e
        if attempt < retries - 1:
            await asyncio.sleep(delay * (attempt + 1))
    if last_exc:
        logger.warning("fetch_with_retry failed: %s | %s", last_exc, url)
    return None


async def download_bytes(url: str, timeout: float = 20.0) -> Optional[bytes]:
    try:
        async with httpx.AsyncClient(timeout=timeout) as client:
            resp = await client.get(url)
            resp.raise_for_status()
            return resp.content
    except Exception as e:
        logger.warning("download_bytes failed: %s | %s", e, url)
        return None


# ============================================================
# توابع قیمت
# ============================================================
def fmt_price(price: float) -> str:
    if price == 0:
        return "0"
    if price < 0.0001:
        return f"{price:.10f}".rstrip("0").rstrip(".")
    if price < 0.01:
        return f"{price:.8f}".rstrip("0").rstrip(".")
    if price < 1:
        return f"{price:.4f}".rstrip("0").rstrip(".")
    if price < 100:
        return f"{price:.3f}".rstrip("0").rstrip(".")
    return f"{price:,.2f}"


def fmt_volume(v: float) -> str:
    if v <= 0:
        return "—"
    a = abs(v)
    for unit, div in (("B", 1e9), ("M", 1e6), ("K", 1e3)):
        if a >= div:
            return f"{v / div:.2f}{unit}"
    return f"{v:.2f}"


def fmt_change(change: float) -> str:
    icon = "📈" if change >= 0 else "📉"
    return f"{icon} {change:+.2f}%"


async def _fetch_binance(symbol: str) -> Optional[Dict[str, Any]]:
    base = symbol[:-2] if symbol.endswith(".P") else symbol
    urls = [
        f"https://api.binance.com/api/v3/ticker/24hr?symbol={base}",
        f"https://fapi.binance.com/fapi/v1/ticker/24hr?symbol={base}",
    ]
    for i, url in enumerate(urls):
        res = await fetch_with_retry(url)
        if isinstance(res, dict) and "lastPrice" in res:
            return {
                "symbol": base,
                "price": float(res.get("lastPrice", 0)),
                "change": float(res.get("priceChangePercent", 0)),
                "high": float(res.get("highPrice", 0)),
                "low": float(res.get("lowPrice", 0)),
                "volume": float(res.get("volume", 0)),
                "quote_volume": float(res.get("quoteVolume", 0)),
                "market": "futures" if i == 1 else "spot",
            }
    return None


async def _fetch_tradingview(symbol: str) -> Optional[Dict[str, Any]]:
    tv_symbol = TV_MAP.get(symbol)
    if not tv_symbol or RealTimeData is None:
        return None
    try:
        rtd = RealTimeData()
        data_gen = rtd.get_latest_trade_info(exchange_symbol=[tv_symbol])
        for packet in data_gen:
            p = packet.get("p") if isinstance(packet, dict) else None
            if not p:
                continue
            for item in p:
                v = item.get("v") if isinstance(item, dict) else None
                if not isinstance(v, dict):
                    continue
                last_price = v.get("lp") or v.get("last_price")
                if last_price is None:
                    continue
                try:
                    last_price = float(last_price)
                    change_price = float(v.get("ch") or v.get("change") or 0)
                except (TypeError, ValueError):
                    continue
                return {
                    "symbol": symbol,
                    "price": last_price,
                    "change": change_price,
                    "high": 0.0,
                    "low": 0.0,
                    "volume": 0.0,
                    "quote_volume": 0.0,
                    "market": "tradingview",
                }
    except Exception:
        logger.exception("TradingView fallback failed for %s", symbol)
    return None


async def get_price_info(symbol: str) -> Optional[Dict[str, Any]]:
    symbol = (symbol or "").upper().strip()
    if not symbol:
        return None
    if symbol in TV_MAP:
        return await _fetch_tradingview(symbol)
    info = await _fetch_binance(symbol)
    if info:
        return info
    if not any(symbol.endswith(q) for q in COMMON_QUOTES):
        for quote in COMMON_QUOTES:
            info = await _fetch_binance(f"{symbol}{quote}")
            if info:
                return info
    return None


# ============================================================
# توابع UI
# ============================================================
def main_keyboard() -> ReplyKeyboardMarkup:
    return ReplyKeyboardMarkup(
        [
            ["📋 هشدارهای من", "💲 قیمت لحظه‌ای"],
            ["➕ افزودن هشدار", "🗑 حذف هشدار"],
            ["📰 اخبار بازار", "ℹ️ راهنما"],
        ],
        resize_keyboard=True,
    )


def back_keyboard() -> ReplyKeyboardMarkup:
    return ReplyKeyboardMarkup([["↩️ بازگشت"]], resize_keyboard=True)


def alert_list_keyboard(total: int, page: int) -> InlineKeyboardMarkup:
    start = page * ALERTS_PER_PAGE
    end = start + ALERTS_PER_PAGE
    rows: List[List[InlineKeyboardButton]] = []
    nav: List[InlineKeyboardButton] = []
    if page > 0:
        nav.append(InlineKeyboardButton("◀️ قبلی", callback_data=f"LIST:{page - 1}"))
    if end < total:
        nav.append(InlineKeyboardButton("بعدی ▶️", callback_data=f"LIST:{page + 1}"))
    if nav:
        rows.append(nav)
    rows.append([
        InlineKeyboardButton("🔄 بروزرسانی", callback_data=f"LIST:{page}"),
        InlineKeyboardButton("🗑 حذف همه", callback_data="DELALL"),
    ])
    return InlineKeyboardMarkup(rows)


def price_keyboard(symbol: str) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([
        [
            InlineKeyboardButton("📊 چارت 1h", callback_data=f"CHART:{symbol}:1h"),
            InlineKeyboardButton("📊 چارت 4h", callback_data=f"CHART:{symbol}:4h"),
        ],
        [
            InlineKeyboardButton("📊 چارت 1d", callback_data=f"CHART:{symbol}:1d"),
            InlineKeyboardButton("🎯 تنظیم هشدار قیمت", callback_data=f"ADDALERT:{symbol}"),
        ],
    ])


def news_keyboard(category: str) -> InlineKeyboardMarkup:
    def btn(cat: str, label: str) -> InlineKeyboardButton:
        prefix = "• " if cat == category else ""
        return InlineKeyboardButton(f"{prefix}{label}", callback_data=f"NEWS:{cat}:0")
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("🔄 بروزرسانی", callback_data=f"NEWSF:{category}:0")],
        [
            btn("ALL", "🌐 همه"),
            btn("CRYPTO", "🪙 کریپتو"),
            btn("OTHER", "📊 سایر"),
        ],
    ])


# ============================================================
# زمان
# ============================================================
def time_ago(ts: int) -> str:
    diff = max(0, int(time.time()) - int(ts))
    if diff < 60:
        return f"{diff} ثانیه پیش"
    if diff < 3600:
        return f"{diff // 60} دقیقه پیش"
    if diff < 86400:
        return f"{diff // 3600} ساعت پیش"
    if diff < 86400 * 30:
        return f"{diff // 86400} روز پیش"
    try:
        return datetime.fromtimestamp(ts, TEHRAN_TZ).strftime("%Y-%m-%d")
    except Exception:
        return "—"


# ============================================================
# دستورها
# ============================================================
HELP_TEXT = (
    "ℹ️ راهنمای ربات Crypto Alert\n\n"
    "🔹 ساخت هشدار (راحت):\n"
    "  1) روی «💲 قیمت لحظه‌ای» بزن و نماد رو بفرست\n"
    "  2) زیر پیام قیمت، دکمه «🎯 تنظیم هشدار قیمت» رو بزن\n"
    "  3) فقط بنویس: 120000 U (یا فقط 120000 برای پیش‌فرض U)\n\n"
    "🔹 دستورها:\n"
    "  /start  - شروع و نمایش منو\n"
    "  /help   - همین راهنما\n"
    "  /add SYMBOL TARGET U|D - افزودن هشدار (دستی)\n"
    "  /list   - نمایش هشدارها\n"
    "  /delete ID - حذف یک هشدار\n"
    "  /p SYMBOL - قیمت لحظه‌ای (مثل /p BTC)\n"
    "  /chart SYMBOL [TF] - چارت تکنیکال (مثل /chart ETHUSDT 4h)\n"
    "  /news [دسته] - اخبار بازار\n"
    "  /cancel - لغو عملیات جاری\n\n"
    "🔹 نکات:\n"
    "  • می‌تونی فقط «BTC» هم بفرستی، ربات خودش BTCUSDT رو امتحان می‌کنه.\n"
    "  • برای Perpetual Futures آخر نماد .P بذار: BTCUSDT.P\n"
    "  • برای دامیننس: BTC.D، TOTAL، TOTAL2 و ...\n"
    "  • جهت U = بالا رفتن، D = پایین آمدن\n"
)


async def start_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    name = user.first_name if user and user.first_name else "دوست عزیز"
    text = (
        f"سلام {name} 👋\n\n"
        "به ربات «Crypto Alert» خوش اومدی 🚀\n\n"
        "این ربات کمکت می‌کنه:\n"
        "🎯 برای هر ارز هشدار قیمتی بذاری\n"
        "💲 قیمت لحظه‌ای هر نمادی رو ببینی\n"
        "📊 چارت تکنیکال بگیری\n"
        "📰 از اخبار مهم بازار باخبر بشی\n\n"
        "👇 از منوی پایین یکی رو انتخاب کن، یا /help رو بزن."
    )
    await update.message.reply_text(text, reply_markup=main_keyboard())


async def help_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(HELP_TEXT, reply_markup=main_keyboard())


async def cancel_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data.clear()
    await update.message.reply_text("عملیات لغو شد ✅", reply_markup=main_keyboard())


# ============================================================
# ساخت هشدار (نسخه تعاملی inline)
# ============================================================
def _normalize_dir(d: str) -> Optional[str]:
    s = d.strip().lower()
    if s in ("u", "up", "بالا", "صعودی", "↗"):
        return "U"
    if s in ("d", "down", "پایین", "نزولی", "↘"):
        return "D"
    return None


def _parse_alert_input(text: str) -> tuple:
    """Parse '120000 U' or '120000' or '120000d' -> (target_float, 'U'|'D') or (None, error_msg)."""
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
            return ((float(parts[0]), "U"), None)
        except ValueError:
            return (None, "❌ قیمت هدف باید عدد باشد")
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


async def _create_alert_inline(
    update: Update, context: ContextTypes.DEFAULT_TYPE,
    symbol: str, target: float, direction: str,
) -> None:
    chat_id = str(update.effective_chat.id)
    try:
        await context.bot.send_chat_action(chat_id=chat_id, action=ChatAction.TYPING)
    except Exception:
        pass
    info = await get_price_info(symbol)
    if not info:
        await update.message.reply_text(
            f"❌ نماد {symbol} یافت نشد.", reply_markup=main_keyboard()
        )
        return
    alerts = await load_alerts()
    user_alerts = alerts.setdefault(chat_id, [])
    if len(user_alerts) >= MAX_ALERTS_PER_USER:
        await update.message.reply_text(
            f"❌ حداکثر {MAX_ALERTS_PER_USER} هشدار مجاز است.",
            reply_markup=main_keyboard(),
        )
        return
    new_id = max((a.get("ID", 0) for a in user_alerts), default=0) + 1
    user_alerts.append({
        "ID": new_id,
        "symbol": info["symbol"],
        "target": target,
        "Goal": direction,
    })
    await save_alerts(alerts)
    cur = info["price"]
    diff = target - cur
    pct = (diff / cur * 100) if cur else 0
    arrow = "⬆️" if direction == "U" else "⬇️"
    dir_fa = "بالا" if direction == "U" else "پایین"
    text = (
        "✅ هشدار ثبت شد\n\n"
        f"🔖 شناسه: #{new_id}\n"
        f"💎 ارز: {info['symbol']}\n"
        f"💰 قیمت فعلی: {fmt_price(cur)}\n"
        f"🎯 هدف: {fmt_price(target)} {arrow} ({dir_fa})\n"
        f"📏 فاصله تا هدف: {pct:+.2f}%"
    )
    await update.message.reply_text(text, reply_markup=main_keyboard())


async def add_alert_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = str(update.effective_chat.id)
    args = context.args
    if len(args) != 3:
        await update.message.reply_text(
            "❌ فرمت اشتباه است.\n"
            "فرمت صحیح: /add SYMBOL TARGET U|D\n\n"
            "مثال‌ها:\n"
            "  /add BTCUSDT 120000 U\n"
            "  /add ETHUSDT 3000 D\n"
            "  /add BTC.D 55 U"
        )
        return
    symbol_raw, target_str, direction_raw = args
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
    try:
        direction = Direction.from_string(direction_raw)
    except ValueError:
        await update.message.reply_text("❌ جهت باید U (بالا) یا D (پایین) باشد.")
        return
    alerts = await load_alerts()
    user_alerts = alerts.setdefault(chat_id, [])
    if len(user_alerts) >= MAX_ALERTS_PER_USER:
        await update.message.reply_text(
            f"❌ حداکثر {MAX_ALERTS_PER_USER} هشدار مجاز است. لطفاً قبلی‌ها را حذف کنید."
        )
        return
    new_id = max((a.get("ID", 0) for a in user_alerts), default=0) + 1
    user_alerts.append({
        "ID": new_id,
        "symbol": info["symbol"],
        "target": target,
        "Goal": direction.value,
    })
    await save_alerts(alerts)
    cur = info["price"]
    diff = target - cur
    pct = (diff / cur * 100) if cur else 0
    arrow = "⬆️" if direction == Direction.UP else "⬇️"
    text = (
        "✅ هشدار ثبت شد\n\n"
        f"🔖 شناسه: #{new_id}\n"
        f"💎 ارز: {info['symbol']}\n"
        f"💰 قیمت فعلی: {fmt_price(cur)}\n"
        f"🎯 هدف: {fmt_price(target)} {arrow}\n"
        f"📏 فاصله تا هدف: {pct:+.2f}%"
    )
    await update.message.reply_text(text, reply_markup=main_keyboard())


async def _render_alert_list(
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
    for s in symbols:
        info = await get_price_info(s)
        price_cache[s] = info["price"] if info else None
    total = len(user_alerts)
    start = page * ALERTS_PER_PAGE
    end = start + ALERTS_PER_PAGE
    page_alerts = user_alerts[start:end]
    lines = [
        f"📋 هشدارهای شما — صفحه {page + 1} از {(total - 1) // ALERTS_PER_PAGE + 1}\n"
    ]
    for a in page_alerts:
        aid = a["ID"]
        sym = a["symbol"]
        tgt = a["target"]
        arrow = "⬆️" if a["Goal"] == "U" else "⬇️"
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
                    InlineKeyboardButton(f"🗑 #{a['ID']}", callback_data=f"DEL:{a['ID']}"),
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
        except Exception as e:
            if "not modified" not in str(e).lower():
                logger.warning("edit_text failed: %s", e)
    else:
        await bot.send_message(chat_id=int(chat_id), text=text, reply_markup=kb)


async def list_alerts_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await _render_alert_list(str(update.effective_chat.id), context.bot)


async def delete_alert_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = str(update.effective_chat.id)
    args = context.args
    if not args or not args[0].isdigit():
        await update.message.reply_text("❌ فرمت: /delete ID\nمثال: /delete 1")
        return
    del_id = int(args[0])
    alerts = await load_alerts()
    if chat_id not in alerts or not alerts[chat_id]:
        await update.message.reply_text("هیچ هشداری یافت نشد.")
        return
    before = len(alerts[chat_id])
    alerts[chat_id] = [a for a in alerts[chat_id] if a.get("ID") != del_id]
    if len(alerts[chat_id]) == before:
        await update.message.reply_text("❌ هشداری با آن شناسه یافت نشد.")
        return
    if not alerts[chat_id]:
        del alerts[chat_id]
    await save_alerts(alerts)
    await update.message.reply_text(f"✅ هشدار #{del_id} حذف شد.", reply_markup=main_keyboard())


async def price_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not context.args:
        await update.message.reply_text("فرمت: /p SYMBOL\nمثال: /p BTC یا /p BTCUSDT")
        return
    await _send_price(update, context, context.args[0].upper())


async def _send_price(update_or_query, context: ContextTypes.DEFAULT_TYPE, symbol: str):
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
            await update_or_query.message.reply_text(text, reply_markup=price_keyboard(info["symbol"]))
        else:
            await context.bot.send_message(
                chat_id=chat.id, text=text, reply_markup=price_keyboard(info["symbol"])
            )
    except Exception:
        logger.exception("send_price message failed")


async def chart_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not context.args:
        await update.message.reply_text(
            "فرمت: /chart SYMBOL [TF]\n"
            "TF اختیاری: 1m, 5m, 15m, 1h, 4h, 1d, 1w\n"
            "مثال: /chart BTCUSDT 4h"
        )
        return
    symbol = context.args[0].upper()
    tf = context.args[1] if len(context.args) > 1 else "4h"
    await _send_chart_to_chat(
        context.bot, update.effective_chat.id, symbol, tf
    )


async def _send_chart_to_chat(bot: Bot, chat_id: int, symbol: str, tf: str) -> None:
    if not CHART_API_KEY:
        try:
            await bot.send_chat_action(chat_id=chat_id, action=ChatAction.TYPING)
        except Exception:
            pass
        info = await get_price_info(symbol)
        if not info:
            await bot.send_message(chat_id=chat_id, text="❌ نماد یافت نشد و کلید چارت هم تنظیم نیست.")
            return
        ch = info.get("change", 0.0) or 0.0
        text = (
            f"📊 {info['symbol']} ({tf})\n"
            f"💰 قیمت: {fmt_price(info['price'])}\n"
            f"{fmt_change(ch)}"
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
        "&indicators=rsi&theme=dark"
        f"&key={CHART_API_KEY}&_t={int(time.time())}"
    )
    ch = info.get("change", 0.0) or 0.0
    trend = "صعودی 🐂" if ch > 0 else "نزولی 🐻"
    caption = (
        f"📊 {info['symbol']} — {tf}\n"
        f"💰 قیمت: {fmt_price(info['price'])}\n"
        f"{fmt_change(ch)} | روند: {trend}"
    )
    data = await download_bytes(chart_url)
    if not data:
        await bot.send_message(chat_id=chat_id, text="❌ خطا در دریافت چارت از سرور.")
        return
    try:
        await bot.send_photo(chat_id=chat_id, photo=data, caption=caption)
    except Exception as e:
        logger.exception("send_photo failed: %s", e)
        await bot.send_message(chat_id=chat_id, text=caption)


# ============================================================
# اخبار (RSS چند منبع - بدون نیاز به API Key)
# ============================================================
NEWS_SOURCES: List[Dict[str, str]] = [
    {"name": "Crypto.News", "url": "https://crypto.news/feed/"},
    {"name": "Decrypt", "url": "https://decrypt.co/feed"},
    {"name": "Cointelegraph", "url": "https://cointelegraph.com/rss"},
    {"name": "CryptoPotato", "url": "https://cryptopotato.com/feed/"},
    {"name": "U.Today", "url": "https://u.today/rss"},
    {"name": "BeInCrypto", "url": "https://beincrypto.com/feed/"},
    {"name": "Bitcoinist", "url": "https://bitcoinist.com/feed/"},
    {"name": "News.Bitcoin.com", "url": "https://news.bitcoin.com/feed/"},
]

NEWS_CATEGORIES: Dict[str, str] = {
    "ALL": "🌐 همه",
    "CRYPTO": "🪙 کریپتو",
    "OTHER": "📊 سایر",
}
_news_cache: Dict[str, Any] = {"data": [], "time": 0.0}

_HTML_TAG_RE = re.compile(r"<[^>]+>")
_HTML_ENTITY_RE = re.compile(r"&(?:#x?[0-9a-fA-F]+|nbsp|amp|lt|gt|quot|apos|#160|#8217|#8220|#8221|#8230);")


def _strip_html(s: str) -> str:
    if not s:
        return ""
    s = _HTML_TAG_RE.sub(" ", s)
    s = _HTML_ENTITY_RE.sub(" ", s)
    s = re.sub(r"\s+", " ", s).strip()
    return s


def _local_tag(el_tag: str) -> str:
    return el_tag.split("}", 1)[-1] if "}" in el_tag else el_tag


def _child_text(el: Any, names: List[str]) -> str:
    """Find first child whose local tag matches any of names (case-insensitive)."""
    wanted = {n.lower() for n in names}
    for child in list(el):
        if _local_tag(child.tag).lower() in wanted:
            return (child.text or "").strip()
    return ""


def _child_attr(el: Any, names: List[str], attr: str) -> str:
    wanted = {n.lower() for n in names}
    for child in list(el):
        if _local_tag(child.tag).lower() in wanted:
            val = child.get(attr)
            if val:
                return val.strip()
    return ""


def _all_categories(el: Any) -> List[str]:
    out: List[str] = []
    for child in list(el):
        if _local_tag(child.tag).lower() == "category":
            txt = (child.text or "").strip()
            if txt and txt not in out:
                out.append(txt)
    return out


def _parse_date(s: str) -> int:
    if not s:
        return 0
    try:
        dt = parsedate_to_datetime(s)
    except Exception:
        try:
            dt = datetime.fromisoformat(s.replace("Z", "+00:00"))
        except Exception:
            return 0
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return int(dt.timestamp())


def _parse_rss(xml_text: str, source_name: str) -> List[Dict[str, Any]]:
    items: List[Dict[str, Any]] = []
    try:
        root = ET.fromstring(xml_text)
    except ET.ParseError as e:
        logger.warning("RSS parse failed for %s: %s", source_name, e)
        return items
    channel = root.find("channel")
    item_elements = list(channel.findall("item")) if channel is not None else list(root.findall("entry"))
    for el in item_elements:
        try:
            title = _child_text(el, ["title"])
            link = _child_attr(el, ["link"], "href") or _child_text(el, ["link", "guid", "id"])
            desc = _child_text(el, ["description", "summary", "content", "content:encoded"])
            pub = _child_text(el, ["pubDate", "published", "updated", "dc:date"])
            if not title or not link:
                continue
            body = _strip_html(desc)[:400]
            items.append({
                "id": link,
                "title": title,
                "body": body,
                "url": link,
                "source": source_name,
                "categories": "|".join(_all_categories(el)),
                "published_on": _parse_date(pub),
            })
        except Exception:
            continue
    return items


async def _fetch_single_feed(source: Dict[str, str]) -> List[Dict[str, Any]]:
    url = source["url"]
    try:
        async with httpx.AsyncClient(timeout=12.0, follow_redirects=True) as client:
            resp = await client.get(
                url,
                headers={
                    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) CryptoAlertBot/1.0"
                },
            )
            resp.raise_for_status()
            content = resp.text
    except Exception as e:
        logger.warning("Feed fetch failed (%s): %s", source["name"], e)
        return []
    return await asyncio.to_thread(_parse_rss, content, source["name"])


async def fetch_news(force: bool = False) -> List[Dict[str, Any]]:
    now = time.time()
    if not force and _news_cache["data"] and (now - _news_cache["time"]) < NEWS_CACHE_TTL:
        return _news_cache["data"]
    tasks = [_fetch_single_feed(src) for src in NEWS_SOURCES]
    results = await asyncio.gather(*tasks, return_exceptions=True)
    items: List[Dict[str, Any]] = []
    for src, result in zip(NEWS_SOURCES, results):
        if isinstance(result, Exception):
            logger.warning("Feed %s raised: %s", src["name"], result)
            continue
        items.extend(result)
    items.sort(key=lambda x: x.get("published_on", 0), reverse=True)
    seen: set = set()
    deduped: List[Dict[str, Any]] = []
    for it in items:
        u = it.get("url", "")
        if u and u not in seen:
            seen.add(u)
            deduped.append(it)
    if not deduped:
        return _news_cache.get("data") or []
    _news_cache["data"] = deduped
    _news_cache["time"] = now
    logger.info("News cache refreshed: %d unique items from %d sources", len(deduped), len(NEWS_SOURCES))
    return deduped


# ============================================================
# تحلیل اهمیت و طبقه‌بندی خبر
# ============================================================
HIGH_IMPACT_KEYWORDS = frozenset([
    # نهادهای نظارتی و قانونی
    "sec", "cftc", "etf", "spot etf", "blackrock", "fidelity", "grayscale",
    "regulation", "regulatory", "ban", "lawsuit", "enforcement", "subpoena",
    "approval", "rejection", "delist", "delisting",
    # اقتصاد کلان و فدرال رزرو
    "federal reserve", " the fed", "fed ", "powell", "fomc", "interest rate",
    "rate cut", "rate hike", "basis points", "bps", "inflation", "cpi", "ppi",
    "gdp", "recession", "treasury", "fiscal", "hawkish", "dovish",
    # بحران‌ها
    "hack", "hacked", "exploit", "breach", "stolen", "insolvency", "bankruptcy",
    "ftx", "mt. gox", "celsius", "voyager", "terra", "luna", "3ac", "threearrow",
    "liquidat", "margin call", "outage", "halt trading", "halted", "suspend",
    # حرکات بزرگ
    "all-time high", "ath", "record high", "record low", "crash", "surge",
    "rally", "plunge", "whale", "billion-dollar", "billion worth",
    # پذیرش نهادی
    "institutional", "treasury reserve", "corporate treasury", "microstrategy",
    "strategy buys", "etf inflow", "etf outflow",
    # ژئوپلیتیک
    "china", "russia", "south korea", " japan", " india", " eu ", "european union",
    "embargo", "sanction", "tariff", "trump", "biden",
    # رویدادهای پروتکل
    "halving", "ethereum upgrade", "pectra", "dencun", "merge", "shanghai",
    "mainnet launch", "hard fork", "soft fork", "token unlock", "cliff unlock",
    "vesting",
])

CRYPTO_KEYWORDS = frozenset([
    "bitcoin", "btc", "ethereum", "eth ", "ether", "crypto", "cryptocurrency",
    "blockchain", "altcoin", "binance", "coinbase", "kraken", "bybit", "okx",
    "defi", "nft", "stablecoin", "tether", "usdt", "usdc", "dai",
    "solana", "sol ", "cardano", "ada ", "ripple", "xrp", "dogecoin", "doge",
    "polkadot", "dot ", "avalanche", "avax", "polygon", "matic", "chainlink",
    "litecoin", "ltc", "tron", "trx", "shiba", "shib", "toncoin", " ton ",
    "memecoin", "meme coin", "l2 ", "layer 2", "rollup", "zksync", "starknet",
    "arbitrum", "optimism", "uniswap", "aave", "compound", "lido", "curve",
    "staking", "yield farming", "dex", "cex", "exchange", "wallet",
    "bitcoin halving", "miner", "hashrate", "proof of stake", "proof of work",
    "smart contract", "ordinals", "brc-20", "runes", " dao", " ico", "ido",
    "airdrop", "wrapped bitcoin", "wbtc", "token launch",
])


def _score_importance(item: Dict[str, Any]) -> int:
    text = (
        (item.get("title") or "")
        + " "
        + (item.get("body") or "")[:400]
    ).lower()
    score = 0
    for kw in HIGH_IMPACT_KEYWORDS:
        if kw in text:
            score += 2
    ts = item.get("published_on", 0)
    if ts > 0:
        age_hours = (time.time() - ts) / 3600
        if age_hours < 3:
            score += 4
        elif age_hours < 12:
            score += 3
        elif age_hours < 24:
            score += 2
        elif age_hours < 48:
            score += 1
    else:
        score -= 1
    return score


def _is_crypto(item: Dict[str, Any]) -> bool:
    text = (
        (item.get("title") or "")
        + " "
        + (item.get("body") or "")[:300]
        + " "
        + (item.get("categories") or "")
    ).lower()
    for kw in CRYPTO_KEYWORDS:
        if kw in text:
            return True
    return False


# ============================================================
# ترجمه به فارسی (با کش و چند سرویس)
# ============================================================
TRANSLATION_CACHE: Dict[str, str] = {}


async def translate_to_fa(text: str) -> str:
    if not text:
        return text
    work = text.strip()
    if not work:
        return work
    if len(work) > 450:
        work = work[:447] + "..."
    if work in TRANSLATION_CACHE:
        return TRANSLATION_CACHE[work]

    result: Optional[str] = None
    from urllib.parse import quote

    # Lingva
    try:
        url = f"https://lingva.ml/api/v1/en/fa/{quote(work, safe='')}"
        async with httpx.AsyncClient(timeout=8.0) as c:
            r = await c.get(url, headers={"User-Agent": "Mozilla/5.0"})
            if r.status_code == 200:
                data = r.json()
                if isinstance(data, dict) and data.get("translation"):
                    result = str(data["translation"]).strip()
    except Exception:
        pass

    # MyMemory fallback
    if not result:
        try:
            url = f"https://api.mymemory.translated.net/get?q={quote(work, safe='')}&langpair=en|fa"
            async with httpx.AsyncClient(timeout=8.0) as c:
                r = await c.get(url, headers={"User-Agent": "Mozilla/5.0"})
                if r.status_code == 200:
                    data = r.json()
                    td = data.get("responseData", {}).get("translatedText", "")
                    if td and "MYMEMORY WARNING" not in td and "INVALID" not in td:
                        result = str(td).strip()
        except Exception:
            pass

    final = result if result else text
    TRANSLATION_CACHE[work] = final
    return final


def _persian_date(ts: int) -> str:
    try:
        dt = datetime.fromtimestamp(ts, TEHRAN_TZ)
        months_fa = [
            "", "ژانویه", "فوریه", "مارس", "آوریل", "مه", "ژوئن",
            "ژوئیه", "اوت", "سپتامبر", "اکتبر", "نوامبر", "دسامبر",
        ]
        return f"{dt.day} {months_fa[dt.month]} {dt.year}"
    except Exception:
        return "—"


# ============================================================
# انتخاب و رندر اخبار
# ============================================================
TOP_NEWS_LIMIT = 7


def _select_top_news(items: List[Dict[str, Any]], category: str) -> List[Dict[str, Any]]:
    if category == "CRYPTO":
        pool = [a for a in items if a.get("_is_crypto")]
    elif category == "OTHER":
        pool = [a for a in items if not a.get("_is_crypto")]
    else:
        pool = list(items)
    pool.sort(key=lambda x: (x.get("_score", 0), x.get("published_on", 0)), reverse=True)
    return pool[:TOP_NEWS_LIMIT]


async def fetch_news(force: bool = False) -> List[Dict[str, Any]]:
    now = time.time()
    if not force and _news_cache["data"] and (now - _news_cache["time"]) < NEWS_CACHE_TTL:
        return _news_cache["data"]
    tasks = [_fetch_single_feed(src) for src in NEWS_SOURCES]
    results = await asyncio.gather(*tasks, return_exceptions=True)
    items: List[Dict[str, Any]] = []
    for src, result in zip(NEWS_SOURCES, results):
        if isinstance(result, Exception):
            logger.warning("Feed %s raised: %s", src["name"], result)
            continue
        items.extend(result)
    seen: set = set()
    deduped: List[Dict[str, Any]] = []
    for it in items:
        u = it.get("url", "")
        if u and u not in seen:
            seen.add(u)
            deduped.append(it)
    if not deduped:
        return _news_cache.get("data") or []
    for it in deduped:
        it["_score"] = _score_importance(it)
        it["_is_crypto"] = _is_crypto(it)
    deduped.sort(key=lambda x: (x.get("_score", 0), x.get("published_on", 0)), reverse=True)
    _news_cache["data"] = deduped
    _news_cache["time"] = now
    logger.info("News cache refreshed: %d unique items", len(deduped))
    return deduped


async def _render_news(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
    category: str = "ALL",
    edit: bool = False,
) -> None:
    if category not in NEWS_CATEGORIES:
        category = "ALL"
    items = await fetch_news()
    if not items:
        text = "❌ دریافت اخبار از سرور ناموفق بود. لطفاً بعداً تلاش کنید."
        if edit and update.message:
            try:
                await update.message.edit_text(text, reply_markup=news_keyboard(category))
            except Exception:
                pass
        elif update.message:
            await update.message.reply_text(text, reply_markup=news_keyboard(category))
        return

    top = _select_top_news(items, category)
    if not top:
        text = (
            f"📭 موردی برای دسته {NEWS_CATEGORIES[category]} پیدا نشد.\n"
            "🔄 بروزرسانی کن یا دسته دیگری انتخاب کن."
        )
        if edit and update.message:
            try:
                await update.message.edit_text(text, reply_markup=news_keyboard(category))
            except Exception:
                pass
        elif update.message:
            await update.message.reply_text(text, reply_markup=news_keyboard(category))
        return

    cat_label = NEWS_CATEGORIES[category]
    header_ts = int(time.time())
    lines = [
        "📰 *اخبار مهم بازار*",
        f"📅 {_persian_date(header_ts)} | دسته: {cat_label}",
        "",
    ]
    for i, art in enumerate(top, start=1):
        title_en = (art.get("title") or "—").strip()
        src = art.get("source") or "—"
        ts = int(art.get("published_on") or 0)
        ago = time_ago(ts) if ts else "—"
        url = art.get("url") or ""
        # ترجمه عنوان
        title_fa = await translate_to_fa(title_en)
        if title_fa and title_fa.strip() and title_fa != title_en:
            lines.append(f"{i}. *{title_fa.strip()}*")
        else:
            lines.append(f"{i}. *{title_en}*")
        lines.append(f"   🗞 {src} • 🕐 {ago}")
        if url:
            lines.append(f"   🔗 {url}")
        lines.append("")

    text = "\n".join(lines).rstrip()
    if len(text) > 4000:
        text = text[:3990] + "..."
    kb = news_keyboard(category)
    if edit and update.message:
        try:
            await update.message.edit_text(
                text, reply_markup=kb, disable_web_page_preview=True,
                parse_mode="Markdown",
            )
        except Exception as e:
            if "not modified" not in str(e).lower():
                logger.warning("edit news failed: %s", e)
                try:
                    await update.message.edit_text(
                        text, reply_markup=kb, disable_web_page_preview=True
                    )
                except Exception:
                    pass
    elif update.message:
        try:
            await update.message.reply_text(
                text, reply_markup=kb, disable_web_page_preview=True,
                parse_mode="Markdown",
            )
        except Exception:
            await update.message.reply_text(
                text, reply_markup=kb, disable_web_page_preview=True
            )


async def news_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    category = "ALL"
    if context.args:
        arg = context.args[0].upper()
        if arg in NEWS_CATEGORIES:
            category = arg
    try:
        await update.effective_chat.send_action(ChatAction.TYPING)
    except Exception:
        pass
    await _render_news(update, context, category=category, edit=False)


# ============================================================
# پیام آزاد (دکمه‌های منو)
# ============================================================
MENU_BUTTONS: Dict[str, str] = {
    "📋 هشدارهای من": "list",
    "💲 قیمت لحظه‌ای": "price",
    "➕ افزودن هشدار": "add",
    "🗑 حذف هشدار": "delete",
    "📰 اخبار بازار": "news",
    "ℹ️ راهنما": "help",
    "↩️ بازگشت": "back",
}


async def handle_free_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not update.message or not update.message.text:
        return
    text = update.message.text.strip()

    # حالت انتظار برای هشدار inline
    pending_sym = context.user_data.get("expecting_alert_symbol")
    if pending_sym:
        context.user_data.pop("expecting_alert_symbol", None)
        result, err = _parse_alert_input(text)
        if err:
            context.user_data["expecting_alert_symbol"] = pending_sym
            await update.message.reply_text(
                f"{err}\n\nدوباره فقط قیمت و جهت رو بفرست.\n"
                f"مثال: `120000 U` یا `3000 D` یا فقط `120000`\n"
                f"برای لغو /cancel یا ↩️ بازگشت بزن.",
                reply_markup=back_keyboard(),
                parse_mode="Markdown",
            )
            return
        target, direction = result
        await _create_alert_inline(update, context, pending_sym, target, direction)
        return

    action = MENU_BUTTONS.get(text)
    if action == "list":
        await _render_alert_list(str(update.effective_chat.id), context.bot)
        return
    if action == "price":
        await update.message.reply_text(
            "💲 نام ارز را بفرست:\n\n"
            "مثال: BTC، BTCUSDT، ETHUSDT.P، BTC.D",
            reply_markup=back_keyboard(),
        )
        return
    if action == "add":
        await update.message.reply_text(
            "➕ افزودن هشدار\n\n"
            "راحت‌ترین راه: 💲 قیمت یک ارز رو بگیر، بعد زیر پیام قیمت دکمه\n"
            "«🎯 تنظیم هشدار قیمت» رو بزن. فقط کافیه عدد و U/D بفرستی.\n\n"
            "دستی:\n"
            "  /add SYMBOL TARGET U|D\n\n"
            "مثال‌ها:\n"
            "  /add BTCUSDT 120000 U\n"
            "  /add ETHUSDT 3000 D",
            reply_markup=main_keyboard(),
        )
        return
    if action == "delete":
        await _render_alert_list(str(update.effective_chat.id), context.bot)
        return
    if action == "news":
        await news_cmd(update, context)
        return
    if action == "help":
        await help_cmd(update, context)
        return
    if action == "back":
        context.user_data.clear()
        await update.message.reply_text("بازگشتیم ✅", reply_markup=main_keyboard())
        return
    if SYMBOL_REGEX.match(text):
        await _send_price(update, context, text.upper())
        return


# ============================================================
# پاسخ به دکمه‌های شیشه‌ای
# ============================================================
async def callback_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    if not query:
        return
    try:
        await query.answer()
    except Exception:
        pass
    data = query.data or ""
    chat_id = str(query.message.chat_id) if query.message else ""

    if data.startswith("DEL:"):
        try:
            aid = int(data.split(":", 1)[1])
        except ValueError:
            return
        alerts = await load_alerts()
        if chat_id not in alerts:
            return
        before = len(alerts.get(chat_id, []))
        alerts[chat_id] = [a for a in alerts[chat_id] if a.get("ID") != aid]
        if not alerts[chat_id]:
            del alerts[chat_id]
        await save_alerts(alerts)
        if len(alerts.get(chat_id, [])) < before:
            try:
                await context.bot.answer_callback_query(
                    query.id, text=f"✅ هشدار #{aid} حذف شد", show_alert=False
                )
            except Exception:
                pass
            await _render_alert_list(chat_id, context.bot, page=0, edit_message=query.message)
        else:
            try:
                await context.bot.answer_callback_query(
                    query.id, text="❌ یافت نشد", show_alert=True
                )
            except Exception:
                pass
        return

    if data == "DELALL":
        alerts = await load_alerts()
        count = len(alerts.get(chat_id, []))
        if chat_id in alerts:
            del alerts[chat_id]
            await save_alerts(alerts)
        try:
            await context.bot.answer_callback_query(
                query.id, text=f"✅ {count} هشدار حذف شد", show_alert=True
            )
        except Exception:
            pass
        await _render_alert_list(chat_id, context.bot, page=0, edit_message=query.message)
        return

    if data.startswith("LIST:"):
        try:
            page = int(data.split(":", 1)[1])
        except ValueError:
            page = 0
        await _render_alert_list(chat_id, context.bot, page=page, edit_message=query.message)
        return

    if data.startswith("CHART:"):
        parts = data.split(":")
        symbol = parts[1] if len(parts) > 1 else "BTCUSDT"
        tf = parts[2] if len(parts) > 2 else "4h"
        await _send_chart_to_chat(context.bot, int(chat_id), symbol, tf)
        return

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
                f"قیمت هدف و جهت رو بفرست:\n"
                f"  • `120000 U` — وقتی قیمت به ۱۲۰٬۰۰۰ یا بالاتر برسه\n"
                f"  • `3000 D` — وقتی قیمت به ۳٬۰۰۰ یا پایین‌تر بیاد\n"
                f"  • فقط عدد `120000` — پیش‌فرض U (بالا)\n\n"
                f"برای لغو /cancel یا ↩️ بازگشت بزن.",
                reply_markup=back_keyboard(),
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

    if data.startswith("NEWS:") or data.startswith("NEWSF:"):
        force = data.startswith("NEWSF:")
        parts = data.split(":")
        category = parts[1] if len(parts) > 1 and parts[1] in NEWS_CATEGORIES else "ALL"
        if force:
            _news_cache["data"] = []
            _news_cache["time"] = 0.0
        try:
            await context.bot.send_chat_action(chat_id=int(chat_id), action=ChatAction.TYPING)
        except Exception:
            pass
        await _render_news(update, context, category=category, edit=True)
        return


# ============================================================
# تسک پس‌زمینه: بررسی هشدارها
# ============================================================
async def check_alerts(bot: Bot):
    while True:
        try:
            alerts = await load_alerts()
            updated: Dict[str, Any] = {}
            price_cache: Dict[str, Optional[Dict[str, Any]]] = {}
            for chat_id, user_alerts in list(alerts.items()):
                if not user_alerts:
                    continue
                remaining: List[Dict[str, Any]] = []
                for alert in list(user_alerts):
                    try:
                        symbol = alert.get("symbol")
                        if not symbol:
                            continue
                        if symbol in price_cache:
                            info = price_cache[symbol]
                        else:
                            info = await get_price_info(symbol)
                            price_cache[symbol] = info
                        if not info or "price" not in info:
                            remaining.append(alert)
                            continue
                        price = float(info["price"])
                        change = info.get("change")
                        target = float(alert["target"])
                        try:
                            direction = Direction.from_string(alert.get("Goal", "U"))
                        except ValueError:
                            remaining.append(alert)
                            continue
                        triggered = (
                            (direction == Direction.UP and price >= target)
                            or (direction == Direction.DOWN and price <= target)
                        )
                        if triggered:
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
                        logger.exception("alert processing error: %s | %s", alert, chat_id)
                        remaining.append(alert)
                if remaining:
                    updated[chat_id] = remaining
            await save_alerts(updated)
        except asyncio.CancelledError:
            logger.info("check_alerts cancelled, exiting")
            raise
        except Exception:
            logger.exception("[check_alerts] fatal error; sleeping 5s")
            await asyncio.sleep(5)
            continue
        await asyncio.sleep(PRICE_CHECK_INTERVAL)


# ============================================================
# هندلر خطا
# ============================================================
async def error_handler(update: object, context: ContextTypes.DEFAULT_TYPE):
    logger.exception("Unhandled exception", exc_info=context.error)
    if isinstance(update, Update) and update.effective_chat:
        try:
            await context.bot.send_message(
                chat_id=update.effective_chat.id,
                text="❌ خطایی رخ داد. لطفاً دوباره تلاش کنید.",
            )
        except Exception:
            pass


# ============================================================
# Main
# ============================================================
def main():
    if not os.path.exists(ALERTS_FILE):
        try:
            with open(ALERTS_FILE, "w", encoding="utf-8") as f:
                json.dump({}, f)
        except Exception:
            logger.exception("Could not create initial alerts file")
    logger.info("BOT IS STARTING ...")
    app = ApplicationBuilder().token(TELEGRAM_TOKEN).build()
    app.add_error_handler(error_handler)
    app.add_handler(CommandHandler("start", start_cmd))
    app.add_handler(CommandHandler("help", help_cmd))
    app.add_handler(CommandHandler("cancel", cancel_cmd))
    app.add_handler(CommandHandler("add", add_alert_cmd))
    app.add_handler(CommandHandler("list", list_alerts_cmd))
    app.add_handler(CommandHandler("delete", delete_alert_cmd))
    app.add_handler(CommandHandler("p", price_cmd))
    app.add_handler(CommandHandler("chart", chart_cmd))
    app.add_handler(CommandHandler("news", news_cmd))
    app.add_handler(CallbackQueryHandler(callback_handler))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_free_message))

    async def _on_startup(application: Any) -> None:
        bot = application.bot
        logger.info("Launching check_alerts background task")

        async def _runner() -> None:
            await check_alerts(bot)

        task = asyncio.create_task(_runner())

        def _on_done(t: asyncio.Task) -> None:
            try:
                exc = t.exception()
            except (asyncio.CancelledError, asyncio.InvalidStateError):
                return
            if exc and not isinstance(exc, asyncio.CancelledError):
                logger.exception("check_alerts crashed: %s; restarting in 5s", exc)
                asyncio.get_event_loop().call_later(
                    5, lambda: asyncio.create_task(check_alerts(bot))
                )

        task.add_done_callback(_on_done)

    app.post_init = _on_startup
    app.run_polling()


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
