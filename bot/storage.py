"""ذخیره‌سازی JSON با کش in-memory و lock مجزا برای هر فایل."""
from __future__ import annotations

import asyncio
import json
import logging
import os
from datetime import datetime
from typing import Any, Dict, Tuple

from .config import (
    ALERTS_FILE,
    CHART_USAGE_FILE,
    PENDING_REQUESTS_FILE,
    SUBSCRIBERS_FILE,
    SUBSCRIPTIONS_FILE,
    logger,
)

_file_locks: Dict[str, asyncio.Lock] = {}
_cache: Dict[str, Any] = {}
_cache_loaded: set = set()


def _get_lock(path: str) -> asyncio.Lock:
    if path not in _file_locks:
        _file_locks[path] = asyncio.Lock()
    return _file_locks[path]


def _load_sync(path: str, default: Any) -> Any:
    if not os.path.exists(path):
        return default
    try:
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
            return data if data is not None else default
    except (json.JSONDecodeError, OSError):
        logger.exception("Failed to load %s", path)
        return default


def _save_sync(path: str, data: Any) -> None:
    tmp = path + ".tmp"
    os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    os.replace(tmp, path)


async def load_json(path: str, default: Any) -> Any:
    """بارگذاری JSON. اگر در کش باشد، از کش برمی‌گرداند (بدون I/O)."""
    if path in _cache_loaded:
        return _cache.get(path, default)
    async with _get_lock(path):
        if path in _cache_loaded:
            return _cache.get(path, default)
        data = await asyncio.to_thread(_load_sync, path, default)
        _cache[path] = data
        _cache_loaded.add(path)
        return data


async def save_json(path: str, data: Any) -> None:
    """ذخیره JSON در فایل و به‌روزرسانی کش."""
    _cache[path] = data
    _cache_loaded.add(path)
    async with _get_lock(path):
        await asyncio.to_thread(_save_sync, path, data)


# --- Alerts ---
async def load_alerts() -> dict:
    return await load_json(ALERTS_FILE, {})


async def save_alerts(data: dict) -> None:
    await save_json(ALERTS_FILE, data)


# --- Subscribers (set of chat_ids) ---
async def load_subscribers() -> set:
    data = await load_json(SUBSCRIBERS_FILE, [])
    return {int(x) for x in data if isinstance(x, (int, str))}


async def save_subscribers(subs: set) -> None:
    await save_json(SUBSCRIBERS_FILE, sorted(subs))


# --- Subscriptions (plan per chat_id) ---
async def load_subscriptions() -> dict:
    return await load_json(SUBSCRIPTIONS_FILE, {})


async def save_subscriptions(data: dict) -> None:
    await save_json(SUBSCRIPTIONS_FILE, data)


# --- Chart usage (per chat, per day) ---
async def load_chart_usage() -> dict:
    return await load_json(CHART_USAGE_FILE, {})


async def save_chart_usage(data: dict) -> None:
    await save_json(CHART_USAGE_FILE, data)


# --- Pending purchase requests (برای پنل ادمین) ---
async def load_pending_requests() -> dict:
    return await load_json(PENDING_REQUESTS_FILE, {})


async def save_pending_requests(data: dict) -> None:
    await save_json(PENDING_REQUESTS_FILE, data)


def _today_str() -> str:
    return datetime.now().strftime("%Y-%m-%d")


async def check_and_increment_chart(chat_id: int) -> Tuple[bool, int, int]:
    """(allowed, used, limit) — اگر allowed=True، شمارنده افزایش یافته."""
    from .subscriptions import get_subscription

    sub = await get_subscription(chat_id)
    limit = sub.effective_plan.max_charts_per_day  # منقضی → FREE

    data = await load_chart_usage()
    key = str(chat_id)
    today = _today_str()

    record = data.get(key, {"date": today, "count": 0})
    if record.get("date") != today:
        record = {"date": today, "count": 0}

    if limit != -1 and record["count"] >= limit:
        return False, record["count"], limit

    record["count"] += 1
    data[key] = record
    await save_chart_usage(data)
    return True, record["count"], limit


async def get_chart_usage_today(chat_id: int) -> Tuple[int, int]:
    """(used, limit) — فقط خواندن، بدون افزایش."""
    from .subscriptions import get_subscription

    sub = await get_subscription(chat_id)
    limit = sub.effective_plan.max_charts_per_day  # منقضی → FREE

    data = await load_chart_usage()
    key = str(chat_id)
    today = _today_str()
    record = data.get(key, {"date": today, "count": 0})
    if record.get("date") != today:
        return 0, limit
    return record.get("count", 0), limit
