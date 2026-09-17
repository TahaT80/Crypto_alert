"""دریافت قیمت از CoinGecko و TradingView — بهینه‌شده با کش و batch."""
from __future__ import annotations

import asyncio
import time
from typing import Any, Dict, List, Optional
from collections import OrderedDict

from .config import (
    COMMON_QUOTES,
    PRICE_CACHE_TTL,
    SYMBOL_SHORTCUTS,
    TV_MAP,
    _RealTimeData,
    logger,
)
from .http_client import fetch_with_retry


# ── Price cache (TTL = PRICE_CACHE_TTL ثانیه, LRU) ─────────

_PRICE_CACHE_MAX = 100
_price_cache: OrderedDict[str, Dict[str, Any]] = OrderedDict()
_price_cache_time: Dict[str, float] = {}


def _cache_get(symbol: str) -> Optional[Dict[str, Any]]:
    ts = _price_cache_time.get(symbol, 0)
    if time.monotonic() - ts < PRICE_CACHE_TTL:
        return _price_cache.get(symbol)
    return None


def _cache_set(symbol: str, data: Dict[str, Any]) -> None:
    if symbol in _price_cache:
        _price_cache.move_to_end(symbol)

    _price_cache[symbol] = data
    _price_cache_time[symbol] = time.monotonic()

    if len(_price_cache) > _PRICE_CACHE_MAX:
        oldest = next(iter(_price_cache))
        _price_cache.pop(oldest)
        _price_cache_time.pop(oldest, None)


def _cache_bulk(symbols: List[str]) -> Dict[str, Optional[Dict[str, Any]]]:
    now = time.monotonic()
    result = {}

    for s in symbols:
        ts = _price_cache_time.get(s, 0)

        if now - ts < PRICE_CACHE_TTL:
            result[s] = _price_cache.get(s)

    return result


# ── CoinGecko symbol → CoinGecko ID ───────────────────────

COINGECKO_MAP = {
    "BTC": "bitcoin",
    "ETH": "ethereum",
    "BNB": "binancecoin",
    "SOL": "solana",
    "XRP": "ripple",
    "ADA": "cardano",
    "DOGE": "dogecoin",
    "TRX": "tron",
    "DOT": "polkadot",
    "MATIC": "matic-network",
    "POL": "polygon-ecosystem-token",
    "LTC": "litecoin",
    "BCH": "bitcoin-cash",
    "LINK": "chainlink",
    "AVAX": "avalanche-2",
    "ATOM": "cosmos",
    "UNI": "uniswap",
    "ETC": "ethereum-classic",
    "XLM": "stellar",
    "FIL": "filecoin",
    "APT": "aptos",
    "ARB": "arbitrum",
    "OP": "optimism",
    "SUI": "sui",
    "PEPE": "pepe",
    "SHIB": "shiba-inu",
    "TON": "the-open-network",
    "NEAR": "near",
    "ICP": "internet-computer",
    "AAVE": "aave",
    "MKR": "maker",
    "CRV": "curve-dao-token",
    "INJ": "injective-protocol",
    "TIA": "celestia",
    "SEI": "sei-network",
    "WIF": "dogwifcoin",
}


def _normalize_symbol(symbol: str) -> str:
    """
    تبدیل نمادهایی مثل BTCUSDT یا BTC به BTC.
    """
    symbol = symbol.upper().strip()

    # Perpetual suffix
    if symbol.endswith(".P"):
        symbol = symbol[:-2]

    # Quote currencies
    for quote in ("USDT", "USDC", "BUSD", "USD", "BTC", "ETH"):
        if symbol.endswith(quote) and len(symbol) > len(quote):
            return symbol[:-len(quote)]

    return symbol


async def _fetch_coingecko_single(symbol: str) -> Optional[Dict[str, Any]]:
    """دریافت قیمت یک نماد از CoinGecko."""

    base = _normalize_symbol(symbol)
    coin_id = COINGECKO_MAP.get(base)

    if not coin_id:
        logger.warning("CoinGecko ID not found for symbol: %s", symbol)
        return None

    url = (
        "https://api.coingecko.com/api/v3/coins/markets"
        f"?vs_currency=usd"
        f"&ids={coin_id}"
        f"&price_change_percentage=24h"
    )

    try:
        res = await fetch_with_retry(url, timeout=10.0)

        if not isinstance(res, list) or not res:
            logger.warning("Invalid CoinGecko response for %s: %s", symbol, res)
            return None

        data = res[0]

        price = data.get("current_price")

        if price is None:
            return None

        info = {
            "symbol": base,
            "price": float(price),
            "change": float(data.get("price_change_percentage_24h") or 0),
            "high": float(data.get("high_24h") or 0),
            "low": float(data.get("low_24h") or 0),
            "volume": float(data.get("total_volume") or 0),
            "quote_volume": float(data.get("total_volume") or 0),
            "market": "coingecko",
        }

        _cache_set(symbol, info)

        return info

    except Exception:
        logger.exception("CoinGecko request failed for %s", symbol)
        return None


# ── TradingView fallback ──────────────────────────────────

async def _fetch_tradingview(symbol: str) -> Optional[Dict[str, Any]]:
    tv_symbol = TV_MAP.get(symbol)

    if not tv_symbol or _RealTimeData is None:
        return None

    loop = asyncio.get_running_loop()

    try:
        rtd = _RealTimeData()

        data_gen = await loop.run_in_executor(
            None,
            rtd.get_latest_trade_info,
            [tv_symbol],
        )

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
                    change_price = float(
                        v.get("ch") or v.get("change") or 0
                    )
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
        logger.exception(
            "TradingView fallback failed for %s",
            symbol,
        )

    return None


# ── Single price ───────────────────────────────────────────

async def get_price_info(symbol: str) -> Optional[Dict[str, Any]]:
    symbol = (symbol or "").upper().strip()

    if not symbol:
        return None

    # Shortcut مثل BTC → BTCUSDT
    symbol = SYMBOL_SHORTCUTS.get(symbol, symbol)

    cached = _cache_get(symbol)

    if cached is not None:
        return cached

    # اول CoinGecko
    info = await _fetch_coingecko_single(symbol)

    if info:
        return info

    # سپس TradingView
    if symbol in TV_MAP:
        info = await _fetch_tradingview(symbol)

        if info:
            return info

    return None


# ── Batch prices ───────────────────────────────────────────

async def get_prices_batch(
    symbols: List[str],
) -> Dict[str, Optional[Dict[str, Any]]]:
    """دریافت قیمت چند نماد — ابتدا از کش، سپس موازی از CoinGecko."""

    unique = list(
        {
            SYMBOL_SHORTCUTS.get(
                s.upper().strip(),
                s.upper().strip(),
            )
            for s in symbols
            if s
        }
    )

    if not unique:
        return {}

    cached = _cache_bulk(unique)

    uncached = [
        s for s in unique
        if s not in cached
    ]

    if uncached:
        results = await asyncio.gather(
            *[
                _fetch_coingecko_single(s)
                for s in uncached
            ],
            return_exceptions=True,
        )

        for symbol, result in zip(uncached, results):
            if isinstance(result, dict) and result:
                cached[symbol] = result

    for symbol in unique:
        if symbol not in cached:
            cached[symbol] = None

    return cached
