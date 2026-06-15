"""کیبوردها و دکمه‌های UI."""
from __future__ import annotations

from typing import List

from telegram import InlineKeyboardButton, InlineKeyboardMarkup, ReplyKeyboardMarkup

from .config import ALERTS_PER_PAGE


def main_keyboard() -> ReplyKeyboardMarkup:
    return ReplyKeyboardMarkup(
        [
            ["📋 هشدارهای من", "💲 قیمت لحظه‌ای"],
            ["➕ افزودن هشدار", "🗑 حذف هشدار"],
            ["💎 پلن‌ها", "ℹ️ راهنما"],
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

