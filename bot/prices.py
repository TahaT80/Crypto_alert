"""دریافت قیمت از بایننس و TradingView — بهینه‌شده با کش و batch."""
from __future__ import annotations

import asyncio
import time
from typing import Any, Dict, List, Optional

from .config import (
    COMMON_QUOTES,
    PRICE_CACHE_TTL,
    SYMBOL_SHORTCUTS,
    TV_MAP,
    _RealTimeData,
    logger,
)
from .http_client import fetch_with_retry

# ── Price cache (TTL = PRICE_CACHE_TTL ثانیه) ──────────────
_price_cache: Dict[str, Dict[str, Any]] = {}
_price_cache_time: Dict[str, float] = {}


def _cache_get(symbol: str) -> Optional[Dict[str, Any]]:
    ts = _price_cache_time.get(symbol, 0)
    if time.monotonic() - ts < PRICE_CACHE_TTL:
        return _price_cache.get(symbol)
    return None


def _cache_set(symbol: str, data: Dict[str, Any]) -> None:
    _price_cache[symbol] = data
    _price_cache_time[symbol] = time.monotonic()


def _cache_bulk(symbols: List[str]) -> Dict[str, Optional[Dict[str, Any]]]:
    """برگرداندن قیمت‌های کش‌شده برای نمادهای معتبر."""
    now = time.monotonic()
    result = {}
    for s in symbols:
        ts = _price_cache_time.get(s, 0)
        if now - ts < PRICE_CACHE_TTL:
            result[s] = _price_cache.get(s)
    return result


async def _fetch_binance_batch(symbols: List[str]) -> Dict[str, Dict[str, Any]]:
    """دریافت قیمت چند نماد به صورت موازی با محدودیت concurrency."""
    results: Dict[str, Dict[str, Any]] = {}
    if not symbols:
        return results

    semaphore = asyncio.Semaphore(5)

    async def _fetch_one(sym: str) -> None:
        async with semaphore:
            info = await _fetch_binance_single(sym)
            if info:
                results[sym] = info

    await asyncio.gather(*[_fetch_one(s) for s in symbols], return_exceptions=True)
    return results


async def _fetch_binance_single(symbol: str) -> Optional[Dict[str, Any]]:
    """دریافت قیمت یک نماد از بایننس (spot + futures)."""
    base = symbol[:-2] if symbol.endswith(".P") else symbol
    urls = [
        f"https://api.binance.com/api/v3/ticker/24hr?symbol={base}",
        f"https://fapi.binance.com/fapi/v1/ticker/24hr?symbol={base}",
    ]
    for i, url in enumerate(urls):
        res = await fetch_with_retry(url, timeout=8.0)
        if isinstance(res, dict) and "lastPrice" in res:
            info = {
                "symbol": base,
                "price": float(res.get("lastPrice", 0)),
                "change": float(res.get("priceChangePercent", 0)),
                "high": float(res.get("highPrice", 0)),
                "low": float(res.get("lowPrice", 0)),
                "volume": float(res.get("volume", 0)),
                "quote_volume": float(res.get("quoteVolume", 0)),
                "market": "futures" if i == 1 else "spot",
            }
            _cache_set(symbol, info)
            return info
    return None


async def _fetch_tradingview(symbol: str) -> Optional[Dict[str, Any]]:
    tv_symbol = TV_MAP.get(symbol)
    if not tv_symbol or _RealTimeData is None:
        return None
    try:
        rtd = _RealTimeData()
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
                info = {
                    "symbol": symbol,
                    "price": last_price,
                    "change": change_price,
                    "high": 0.0,
                    "low": 0.0,
                    "volume": 0.0,
                    "quote_volume": 0.0,
                    "market": "tradingview",
                }
                _cache_set(symbol, info)
                return info
    except Exception:
        logger.exception("TradingView fallback failed for %s", symbol)
    return None


async def get_price_info(symbol: str) -> Optional[Dict[str, Any]]:
    symbol = (symbol or "").upper().strip()
    if not symbol:
        return None

    # اگر نماد کوتاه باشد (مثل BTC)، به نماد کامل تبدیل کن
    symbol = SYMBOL_SHORTCUTS.get(symbol, symbol)

    cached = _cache_get(symbol)
    if cached is not None:
        return cached

    if symbol in TV_MAP:
        return await _fetch_tradingview(symbol)

    info = await _fetch_binance_single(symbol)
    if info:
        return info

    # اگر نماد با quote تمام نشد، quoteها را امتحان کن ( موازی )
    if not any(symbol.endswith(q) for q in COMMON_QUOTES):
        results = await asyncio.gather(
            *[_fetch_binance_single(f"{symbol}{q}") for q in COMMON_QUOTES],
            return_exceptions=True,
        )
        for r in results:
            if isinstance(r, dict) and r:
                return r
    return None


async def get_prices_batch(symbols: List[str]) -> Dict[str, Optional[Dict[str, Any]]]:
    """دریافت قیمت چند نماد — ابتدا از کش، سپس موازی از API."""
    unique = list({SYMBOL_SHORTCUTS.get(s.upper().strip(), s.upper().strip()) for s in symbols if s})
    if not unique:
        return {}

    cached = _cache_bulk(unique)
    uncached = [s for s in unique if s not in cached]

    if uncached:
        fetched = await _fetch_binance_batch(uncached)
        for s, info in fetched.items():
            cached[s] = info

    for s in unique:
        if s not in cached:
            cached[s] = None

    return cached
