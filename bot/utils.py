"""توابع کمکی: قالب‌بندی، زمان."""
from __future__ import annotations

import time
from datetime import datetime

from .config import TEHRAN_TZ


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


_PERSIAN_MONTHS = [
    "", "ژانویه", "فوریه", "مارس", "آوریل", "مه", "ژوئن",
    "ژوئیه", "اوت", "سپتامبر", "اکتبر", "نوامبر", "دسامبر",
]


def persian_date(ts: int) -> str:
    try:
        dt = datetime.fromtimestamp(ts, TEHRAN_TZ)
        return f"{dt.day} {_PERSIAN_MONTHS[dt.month]} {dt.year}"
    except Exception:
        return "—"
