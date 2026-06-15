"""کلاینت HTTP مشترک با Connection Pool بهینه‌شده."""
from __future__ import annotations

import asyncio
from typing import Any, Dict, Optional

import httpx

from .config import HTTP_CONNECT_TIMEOUT, HTTP_TIMEOUT_GENERAL, logger

_shared_client: Optional[httpx.AsyncClient] = None


def get_client() -> httpx.AsyncClient:
    """کلاینت مشترک (lazy init). هر فراخوانی همان instance را برمی‌گرداند."""
    global _shared_client
    if _shared_client is None:
        limits = httpx.Limits(
            max_connections=15,
            max_keepalive_connections=8,
            keepalive_expiry=60.0,
        )
        try:
            _shared_client = httpx.AsyncClient(
                timeout=httpx.Timeout(
                    HTTP_TIMEOUT_GENERAL, connect=HTTP_CONNECT_TIMEOUT
                ),
                limits=limits,
                follow_redirects=True,
                headers={"User-Agent": "Mozilla/5.0 (compatible; CryptoAlertBot/3.0)"},
                http2=True,
            )
        except TypeError:
            _shared_client = httpx.AsyncClient(
                timeout=httpx.Timeout(
                    HTTP_TIMEOUT_GENERAL, connect=HTTP_CONNECT_TIMEOUT
                ),
                limits=limits,
                follow_redirects=True,
                headers={"User-Agent": "Mozilla/5.0 (compatible; CryptoAlertBot/3.0)"},
            )
    return _shared_client


async def close_client() -> None:
    """در shutdown فراخوانی شود تا connectionها بسته شوند."""
    global _shared_client
    if _shared_client is not None:
        try:
            await _shared_client.aclose()
        except Exception:
            pass
        _shared_client = None


async def fetch_with_retry(
    url: str,
    retries: int = 2,
    delay: float = 1.0,
    timeout: float = HTTP_TIMEOUT_GENERAL,
    *,
    headers: Optional[Dict[str, str]] = None,
) -> Optional[Any]:
    last_exc: Optional[Exception] = None
    client = get_client()
    for attempt in range(retries):
        try:
            resp = await client.get(url, headers=headers or {}, timeout=timeout)
            if resp.status_code == 400:
                return None
            if resp.status_code in (429, 500, 502, 503, 504):
                last_exc = httpx.HTTPStatusError(
                    "retryable", request=resp.request, response=resp
                )
            else:
                resp.raise_for_status()
                ct = resp.headers.get("content-type", "")
                if "application/json" in ct:
                    return resp.json()
                return resp.text
        except (httpx.HTTPError, asyncio.TimeoutError) as exc:
            last_exc = exc
        if attempt < retries - 1:
            await asyncio.sleep(delay * (attempt + 1))
    if last_exc:
        logger.warning("fetch_with_retry failed: %s | %s", last_exc, url)
    return None


async def download_bytes(url: str, timeout: float = 20.0) -> Optional[bytes]:
    try:
        client = get_client()
        resp = await client.get(url, timeout=timeout)
        resp.raise_for_status()
        return resp.content
    except Exception as exc:
        logger.warning("download_bytes failed: %s | %s", exc, url)
        return None
