"""پیکربندی و ثابت‌های برنامه."""
from __future__ import annotations

import logging
import os
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict

from dotenv import load_dotenv

load_dotenv(Path(__file__).resolve().parent.parent / ".env")


def _env(key: str, default: str = "") -> str:
    return os.getenv(key, default).strip()


# ── Telegram & API keys ────────────────────────────────────
TELEGRAM_TOKEN: str = _env("TELEGRAM_TOKEN") or _env("TELEGRAM_BOT_TOKEN")
if not TELEGRAM_TOKEN:
    raise RuntimeError("❌ TELEGRAM_TOKEN در .env تنظیم نشده است.")

CHART_API_KEY: str = _env("CHART_API_KEY")

# ── Timezone ───────────────────────────────────────────────
TIMEZONE: str = _env("TIMEZONE", "Asia/Tehran")

# ── Storage paths ──────────────────────────────────────────
DATA_DIR = Path(__file__).resolve().parent.parent / "data"
DATA_DIR.mkdir(exist_ok=True)
ALERTS_FILE = str(DATA_DIR / "alerts.json")
SUBSCRIBERS_FILE = str(DATA_DIR / "subscribers.json")
SUBSCRIPTIONS_FILE = str(DATA_DIR / "subscriptions.json")
CHART_USAGE_FILE = str(DATA_DIR / "chart_usage.json")
PENDING_REQUESTS_FILE = str(DATA_DIR / "pending_requests.json")

# ── Tunables ───────────────────────────────────────────────
PRICE_CHECK_INTERVAL = 60
PRICE_CACHE_TTL = 25
ALERTS_PER_PAGE = 8
MAX_ALERTS_PER_USER = 50

# ── Timeouts ───────────────────────────────────────────────
HTTP_TIMEOUT_GENERAL = 15.0
HTTP_CONNECT_TIMEOUT = 10.0
HTTP_TIMEOUT_TELEGRAM_CONNECT = 20.0
HTTP_TIMEOUT_TELEGRAM_READ = 45.0

# ── TradingView symbols ───────────────────────────────────
TV_MAP: Dict[str, str] = {
    "BTC.D": "CRYPTOCAP:BTC.D",
    "ETH.D": "CRYPTOCAP:ETH.D",
    "TOTAL": "CRYPTOCAP:TOTAL",
    "TOTAL2": "CRYPTOCAP:TOTAL2",
    "TOTAL3": "CRYPTOCAP:TOTAL3",
}
COMMON_QUOTES = ("USDT", "FDUSD", "USDC", "BTC", "ETH")
SYMBOL_REGEX = re.compile(r"^[A-Za-z0-9.\-]{2,20}$")

SYMBOL_SHORTCUTS: Dict[str, str] = {
    "BTC": "BTCUSDT", "ETH": "ETHUSDT", "SOL": "SOLUSDT",
    "BNB": "BNBUSDT", "XRP": "XRPUSDT", "DOGE": "DOGEUSDT",
    "ADA": "ADAUSDT", "AVAX": "AVAXUSDT", "DOT": "DOTUSDT",
    "LINK": "LINKUSDT", "MATIC": "MATICUSDT", "UNI": "UNIUSDT",
    "LTC": "LTCUSDT", "ATOM": "ATOMUSDT", "FIL": "FILUSDT",
    "NEAR": "NEARUSDT", "APT": "APTUSDT", "ARB": "ARBUSDT",
    "OP": "OPUSDT", "SUI": "SUIUSDT", "PEPE": "PEPEUSDT",
    "SHIB": "SHIBUSDT", "TON": "TONUSDT", "TRX": "TRXUSDT",
}


# ── Plans ──────────────────────────────────────────────────
FREE_FEATURES = (
    "✅ ۳ هشدار قیمت همزمان",
    "✅ ۲ نمودار تکنیکال در روز",
)
PRO_FEATURES = (
    "✅ ۸ هشدار قیمت همزمان",
    "✅ ۸ نمودار تکنیکال در روز",
    "✅ پشتیبانی اولویت‌دار",
    "✅ اشتراک ۱ ماهه",
)
VIP_FEATURES = (
    "✅ هشدار قیمت نامحدود",
    "✅ نمودار تکنیکال نامحدود",
    "✅ دسترسی زودتر به ویژگی‌های جدید",
    "✅ پشتیبانی VIP ۲۴/۷",
    "✅ اشتراک ۱ ماهه",
)


@dataclass(frozen=True)
class Plan:
    code: str
    name_fa: str
    price_toman: int
    price_usd: int
    duration_days: int
    max_alerts: int
    max_charts_per_day: int
    features: tuple
    badge: str

    @property
    def price_text(self) -> str:
        if self.price_toman == 0:
            return "رایگان ♾️"
        return f"{self.price_toman:,} تومان / ماه  (~${self.price_usd})"

    @property
    def duration_text(self) -> str:
        if self.duration_days == 0:
            return "بدون انقضا"
        if self.duration_days == 30:
            return "۱ ماهه"
        if self.duration_days == 365:
            return "۱ ساله"
        return f"{self.duration_days} روز"

    @property
    def max_alerts_text(self) -> str:
        return "∞" if self.max_alerts == -1 else str(self.max_alerts)

    @property
    def max_charts_text(self) -> str:
        return "∞" if self.max_charts_per_day == -1 else f"{self.max_charts_per_day}/روز"


PLANS: Dict[str, Plan] = {
    "FREE": Plan(
        code="FREE", name_fa="رایگان", price_toman=0, price_usd=0,
        duration_days=0, max_alerts=3, max_charts_per_day=2,
        features=FREE_FEATURES, badge="🆓",
    ),
    "PRO": Plan(
        code="PRO", name_fa="حرفه‌ای", price_toman=550_000, price_usd=3,
        duration_days=30, max_alerts=8, max_charts_per_day=8,
        features=PRO_FEATURES, badge="⭐",
    ),
    "VIP": Plan(
        code="VIP", name_fa="ویژه", price_toman=900_000, price_usd=5,
        duration_days=30, max_alerts=-1, max_charts_per_day=-1,
        features=VIP_FEATURES, badge="💎",
    ),
}

DEFAULT_PLAN = "FREE"

# ── Admin IDs ──────────────────────────────────────────────
_admin_ids_raw = _env("ADMIN_IDS", "")
ADMIN_IDS: set = {
    int(_id.strip())
    for _id in _admin_ids_raw.split(",")
    if _id.strip().lstrip("-").isdigit()
}
ADMIN_CONTACT = _env("ADMIN_CONTACT", "@admin")


# ── Logging ────────────────────────────────────────────────
def setup_logging() -> logging.Logger:
    _logger = logging.getLogger("bot")
    _logger.setLevel(logging.INFO)
    _logger.propagate = False
    if not _logger.handlers:
        log_file = os.getenv("BOT_LOG_FILE", "").strip()
        if log_file:
            try:
                _fh = logging.FileHandler(log_file, encoding="utf-8")
                _fh.setFormatter(logging.Formatter("%(asctime)s %(levelname)s: %(message)s"))
                _logger.addHandler(_fh)
            except Exception:
                pass
        _ch = logging.StreamHandler()
        _ch.setFormatter(logging.Formatter("%(asctime)s %(levelname)s: %(message)s"))
        _logger.addHandler(_ch)
    for name in ("httpx", "httpcore", "apscheduler", "telegram.ext._updater"):
        logging.getLogger(name).setLevel(logging.WARNING)
    return _logger


logger = setup_logging()

# ── Timezone ───────────────────────────────────────────────
try:
    from zoneinfo import ZoneInfo
    TEHRAN_TZ: Any = ZoneInfo("Asia/Tehran")
except Exception:
    from datetime import timezone, timedelta
    TEHRAN_TZ = timezone(timedelta(hours=3, minutes=30))

# ── TradingView (optional) ─────────────────────────────────
try:
    from tradingview_scraper.symbols.stream import RealTimeData  # type: ignore
    _RealTimeData: Any = RealTimeData
except Exception:
    _RealTimeData = None  # type: ignore
