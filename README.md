# 🤖 Crypto Alert Bot

<p align="center">
  <a href="#-ویژگی‌ها">ویژگی‌ها</a> •
  <a href="#-نصب-سریع">نصب</a> •
  <a href="#-دستورات">دستورات</a> •
  <a href="#-پنل-ادمین">پنل ادمین</a> •
  <a href="#-استقرار-روی-سرور-لینوکس">استقرار لینوکس</a> •
  <a href="#-داکر">داکر</a> •
  <a href="#-به‌روزرسانی">آپدیت</a> •
  <a href="#-معماری">معماری</a>
</p>

<p align="center">
  <img alt="Python" src="https://img.shields.io/badge/Python-3.10%2B-3776AB?logo=python&logoColor=white" />
  <img alt="python-telegram-bot" src="https://img.shields.io/badge/PTB-21%2B-26A5E4?logo=telegram&logoColor=white" />
  <img alt="License" src="https://img.shields.io/badge/License-MIT-green" />
  <img alt="Platform" src="https://img.shields.io/badge/Platform-Linux%20%7C%20macOS%20%7C%20Windows-lightgrey" />
</p>

بات تلگرام برای **هشدار قیمت لحظه‌ای ارزهای دیجیتال** + **چارت تکنیکال** + **سیستم اشتراک چندسطحی**.

ساخته‌شده با [`python-telegram-bot`](https://github.com/python-telegram-bot/python-telegram-bot) و [`httpx`](https://github.com/encode/httpx)، با معماری ماژولار، async کامل، و پنل مدیریت داخل ربات.

---

## ✨ ویژگی‌ها

### 🔔 هشدار قیمت

- **اسپات و فیوچرز بایننس** به‌صورت یکپارچه
- **TradingView symbols** برای دامیننس (`BTC.D`, `TOTAL`, `TOTAL2`, …)
- **تشخیص خودکار نماد**: `BTC` → `BTCUSDT`، `ETH` → `ETHUSDT` و چندین جفت دیگر
- **تشخیص خودکار جهت**: اگر فقط عدد بفرستی، بالاتر از قیمت فعلی → U، پایین‌تر → D
- **چک هر ۶۰ ثانیه** در پس‌زمینه (parallel برای همه نمادها)
- **دکمه‌های شیشه‌ای** برای حذف، نمایش چارت، بروزرسانی
- **صفحه‌بندی** لیست هشدارها

### 💲 قیمت و چارت

- قیمت لحظه‌ای + اطلاعات ۲۴h (high, low, volume, change%)
- **چارت تکنیکال** با RSI، BB، EMA50 (Chart-Img API)
- تایم‌فریم‌های متنوع: `1m`, `5m`, `15m`, `1h`, `4h`, `1d`, `1w`
- **محدودیت نمودار روزانه** بر اساس پلن

### 💎 پلن‌های اشتراک

| پلن | قیمت/ماه | مدت | هشدار همزمان | نمودار/روز |
|---|---|---|---|---|
| 🆓 **FREE** | رایگان ♾️ | بدون انقضا | ۳ | ۲ |
| ⭐ **PRO** | 550٬000 تومان | ۱ ماهه | ۸ | ۸ |
| 💎 **VIP** | 900٬000 تومان | ۱ ماهه | ∞ | ∞ |

> تنظیم قیمت و محدودیت‌ها فقط با ویرایش `PLANS` در `bot/config.py` — بدون نیاز به ری‌استارت.

### 👑 پنل ادمین

**بدون نیاز به باز کردن کد!** همه‌چیز از داخل ربات:

- 📊 **آمار زنده**: تعداد کاربران هر پلن + منقضی‌ها + درخواست‌های در انتظار
- 📩 **درخواست‌های خرید**: لیست با دکمه‌های **تایید/رد**
- 👥 **لیست کاربران** با صفحه‌بندی
- 🔍 **جستجوی کاربر** با chat_id
- 🔔 **نوتیفیکیشن خودکار** به ادمین‌ها هنگام درخواست خرید

### ⏰ ارسال خودکار

- **تنزل خودکار** پلن‌های منقضی‌شده به FREE (هر شب ۰۰:۰۵ + استارت بات)

---

## 🧰 تکنولوژی

| لایه | ابزار |
|---|---|
| **زبان** | Python 3.10+ |
| **فریم‌ورک بات** | [`python-telegram-bot`](https://github.com/python-telegram-bot/python-telegram-bot) v21+ |
| **HTTP** | [`httpx`](https://github.com/encode/httpx) (async + connection pool) |
| **Scheduler** | [`APScheduler`](https://github.com/agronholm/apscheduler) |
| **TradingView** | [`tradingview-scraper`](https://pypi.org/project/tradingview-scraper/) |
| **ذخیره‌سازی** | JSON (در `data/`) |
| **نمودار** | [chart-img.com](https://chart-img.com) API |
| **لاگ** | stdout → journald (systemd) |

---

## 📁 ساختار پروژه

```
Crypto_alert/
├── main.py                    # نقطه ورود + ثبت هندلرها
├── requirements.txt
├── .env                       # تنظیمات محیطی (ساخته شود)
├── .env.example
├── Dockerfile
├── docker-compose.yml
├── deploy/
│   ├── crypto-alert.service   # systemd unit
│   ├── install.sh             # اسکریپت نصب خودکار
│   └── README.md              # راهنمای deploy
├── bot/
│   ├── __init__.py
│   ├── config.py              # env، ثابت‌ها، پلن‌ها
│   ├── storage.py             # JSON I/O + کش in-memory + per-file lock
│   ├── http_client.py         # کلاینت HTTP مشترک (connection pool)
│   ├── utils.py               # قالب‌بندی، زمان
│   ├── prices.py              # قیمت Binance + TradingView
│   ├── ui.py                  # کیبوردها
│   ├── alerts.py              # CRUD هشدار + تسک پس‌زمینه
│   ├── subscriptions.py       # پلن‌ها + auto-demotion
│   ├── admin.py               # پنل ادمین + pending requests
│   ├── update.py              # startup + shutdown + error handler
│   └── handlers/
│       ├── commands.py        # /start, /plan, /grant, /admin, ...
│       ├── callbacks.py       # دکمه‌ها + پنل ادمین
│       └── messages.py        # پیام‌های آزاد + منو
└── data/                      # JSON ها (auto-created)
    ├── alerts.json
    ├── subscribers.json
    ├── subscriptions.json
    ├── chart_usage.json
    └── pending_requests.json
```

---

## 🚀 نصب سریع

### پیش‌نیازها

- **Python 3.10+** (به‌خاطر `zoneinfo` و `httpx` مدرن)
- یک **توکن ربات تلگرام** از [@BotFather](https://t.me/BotFather)

### مراحل نصب

```bash
# 1. کلون یا دانلود
git clone https://github.com/TahaT80/Crypto_alert.git
cd Crypto_alert

# 2. ساخت محیط مجازی
python3 -m venv venv
source venv/bin/activate        # لینوکس/مک
# venv\Scripts\activate         # ویندوز

# 3. نصب وابستگی‌ها
pip install --upgrade pip
pip install -r requirements.txt

# 4. تنظیم .env
cp .env.example .env
nano .env                        # TELEGRAM_TOKEN را پر کن

# 5. اجرا
python main.py
```

اگر همه‌چی درست باشد:

```
2025-01-15 10:00:00 INFO: 🚀 BOT IS STARTING ...
2025-01-15 10:00:00 INFO: ✅ Scheduler started — demote expired daily at 00:05
2025-01-15 10:00:00 INFO: check_alerts started
2025-01-15 10:00:00 INFO: Application started
```

برو و در تلگرام به رباتت `/start` بفرست.

---

## 🖥 استقرار روی سرور لینوکس

### روش ۱: systemd (توصیه‌شده)

#### مرحله ۱: آماده‌سازی سرور

```bash
# آپدیت سیستم و نصب پیش‌نیازها (Ubuntu/Debian)
sudo apt update && sudo apt upgrade -y
sudo apt install -y python3.11 python3.11-venv python3-pip git

# برای CentOS/RHEL/Rocky/Alma
# sudo dnf install -y python3.11 python3.11-pip git
```

#### مرحله ۲: ساخت کاربر اختصاصی

```bash
# ساخت کاربر سیستمی (بدون دسترسی shell)
sudo useradd -r -s /bin/false -d /opt/crypto-alert crypto-alert

# ساخت پوشه پروژه
sudo mkdir -p /opt/crypto-alert
sudo chown crypto-alert:crypto-alert /opt/crypto-alert
```

#### مرحله ۳: دانلود و نصب پروژه

```bash
# کلون ریپازیتوری
cd /tmp
git clone https://github.com/TahaT80/Crypto_alert.git
cd Crypto_alert

# کپی فایل‌ها به پوشه نهایی
sudo cp -r * /opt/crypto-alert/
sudo cp -r .env.example /opt/crypto-alert/
sudo chown -R crypto-alert:crypto-alert /opt/crypto-alert
```

#### مرحله ۴: ساخت محیط مجازی و نصب وابستگی‌ها

```bash
# ورود به دایرکتوری پروژه
cd /opt/crypto-alert

# ساخت محیط مجازی
sudo -u crypto-alert python3 -m venv /opt/crypto-alert/venv

# نصب وابستگی‌ها
sudo -u crypto-alert /opt/crypto-alert/venv/bin/pip install --upgrade pip
sudo -u crypto-alert /opt/crypto-alert/venv/bin/pip install -r /opt/crypto-alert/requirements.txt
```

#### مرحله ۵: تنظیم فایل محیطی

```bash
# کپی .env.example به .env
sudo -u crypto-alert cp /opt/crypto-alert/.env.example /opt/crypto-alert/.env

# ویرایش فایل .env
sudo -u crypto-alert nano /opt/crypto-alert/.env
```

محتوای `.env` را تنظیم کنید:

```env
# === Telegram ===
TELEGRAM_TOKEN=123456:ABC-DEF...          # الزامی

# === ادمین ===
ADMIN_IDS=123456789,987654321            # آیدی عددی ادمین‌ها
ADMIN_CONTACT=@your_admin                # یوزرنیم ادمین

# === زمان‌بندی ===
TIMEZONE=Asia/Tehran

# === API های اختیاری ===
CHART_API_KEY=                           # برای چارت تکنیکال
```

#### مرحله ۶: ایجاد و فعال‌سازی سرویس systemd

فایل سرویس را بسازید:

```bash
sudo nano /etc/systemd/system/crypto-alert.service
```

محتوای زیر را قرار دهید:

```ini
[Unit]
Description=Crypto Alert Telegram Bot
After=network.target

[Service]
Type=simple
User=crypto-alert
Group=crypto-alert
WorkingDirectory=/opt/crypto-alert
ExecStart=/opt/crypto-alert/venv/bin/python main.py
Restart=always
RestartSec=10
Environment=PYTHONUNBUFFERED=1
StandardOutput=journal
StandardError=journal
SyslogIdentifier=crypto-alert

[Install]
WantedBy=multi-user.target
```

فعال‌سازی و استارت سرویس:

```bash
# ریلود systemd
sudo systemctl daemon-reload

# فعال‌سازی در بوت
sudo systemctl enable crypto-alert

# استارت سرویس
sudo systemctl start crypto-alert

# بررسی وضعیت
sudo systemctl status crypto-alert
```

#### مرحله ۷: مدیریت سرویس

```bash
# مشاهده وضعیت
sudo systemctl status crypto-alert

# استارت
sudo systemctl start crypto-alert

# استاپ
sudo systemctl stop crypto-alert

# ری‌استارت
sudo systemctl restart crypto-alert

# مشاهده لاگ‌ها (زنده)
sudo journalctl -u crypto-alert -f

# مشاهده لاگ‌های اخیر
sudo journalctl -u crypto-alert -n 50

# مشاهده لاگ‌ها از زمان خاص
sudo journalctl -u crypto-alert --since "2025-01-15 10:00"
```

#### مرحله ۸: چک‌لیست نهایی نصب

```bash
# چک کردن اجرای بات
curl -sf https://api.telegram.org/bot${TELEGRAM_TOKEN}/getMe

# چک کردن پورت‌ها
sudo ss -tlnp | grep python

# چک کردن مالکیت فایل‌ها
ls -la /opt/crypto-alert/data/

# چک کردن وضعیت سرویس
systemctl is-enabled crypto-alert
```

---

### روش ۲: اسکریپت نصب خودکار

اگر فایل `deploy/install.sh` موجود باشد:

```bash
# دانلود و اجرا
cd /tmp
git clone https://github.com/TahaT80/Crypto_alert.git
cd Crypto_alert
chmod +x deploy/install.sh
sudo ./deploy/install.sh
```

---

### روش ۳: نصب دستی (بدون systemd)

اگر نمی‌خواهید از systemd استفاده کنید:

```bash
# ورود به پوشه پروژه
cd /opt/crypto-alert

# اجرا با nohup
sudo -u crypto-alert nohup /opt/crypto-alert/venv/bin/python main.py > /var/log/crypto-alert.log 2>&1 &

# یا استفاده از screen
sudo -u crypto-alert screen -dmS crypto-alert /opt/crypto-alert/venv/bin/python main.py

# برای مشاهده screen
screen -r crypto-alert
```

---

## 🔄 به‌روزرسانی

### آپدیت دستی

```bash
# ۱. توقف سرویس
sudo systemctl stop crypto-alert

# ۲. ورود به پوشه پروژه
cd /opt/crypto-alert

# ۳. دریافت تغییرات
sudo -u crypto-alert git pull origin main

# ۴. آپدیت وابستگی‌ها
sudo -u crypto-alert /opt/crypto-alert/venv/bin/pip install -r /opt/crypto-alert/requirements.txt

# ۵. استارت مجدد
sudo systemctl start crypto-alert

# ۶. بررسی وضعیت
sudo systemctl status crypto-alert
```

### اسکریپت آپدیت خودکار

یک فایل بسازید: `sudo nano /opt/crypto-alert/update.sh`

```bash
#!/bin/bash
cd /opt/crypto-alert
sudo systemctl stop crypto-alert
sudo -u crypto-alert git pull origin main
sudo -u crypto-alert /opt/crypto-alert/venv/bin/pip install -r /opt/crypto-alert/requirements.txt
sudo systemctl start crypto-alert
echo "✅ Update completed at $(date)"
```

اجازه اجرا بدهید:

```bash
chmod +x /opt/crypto-alert/update.sh
```

اجرای آپدیت:

```bash
sudo /opt/crypto-alert/update.sh
```

### آپدیت از طریق crontab (خودکار روزانه)

```bash
# ویرایش crontab
sudo crontab -e

# اضافه کردن خط زیر (هر روز ساعت ۴ صبح)
0 4 * * * /opt/crypto-alert/update.sh >> /var/log/crypto-alert-update.log 2>&1
```

---

## ⚙️ پیکربندی

تمام تنظیمات در فایل `.env`:

```env
# === Telegram ===
TELEGRAM_TOKEN=123456:ABC-DEF...          # الزامی

# === ادمین ===
ADMIN_IDS=123456789,987654321            # چند ادمین، با کاما
ADMIN_CONTACT=@your_admin                # یوزرنیم برای نمایش به کاربران

# === زمان‌بندی ===
TIMEZONE=Asia/Tehran

# === API های اختیاری ===
CHART_API_KEY=                           # برای چارت تکنیکال
CMC_API_KEY=                             # CoinMarketCap
```

### متغیرهای کلیدی

| متغیر | الزامی | توضیح |
|---|---|---|
| `TELEGRAM_TOKEN` | ✅ | توکن BotFather |
| `ADMIN_IDS` | ❌ | آیدی عددی ادمین‌ها برای دستورات ادمینی |
| `ADMIN_CONTACT` | ❌ | یوزرنیم ادمین (برای نمایش به کاربران) |
| `CHART_API_KEY` | ❌ | بدون آن فقط متن قیمت (بدون تصویر) |

---

## 💬 دستورات ربات

### دستورات عمومی

| دستور | توضیح |
|---|---|
| `/start` | منوی اصلی + ثبت‌نام خودکار |
| `/help` | راهنمای کامل |
| `/cancel` | لغو عملیات جاری |
| `/add SYM PRICE [U\|D]` | افزودن هشدار قیمت |
| `/list` | لیست هشدارها (با صفحه‌بندی) |
| `/delete ID` | حذف یک هشدار |
| `/p SYM` | قیمت لحظه‌ای |
| `/chart SYM [TF]` | چارت تکنیکال |
| `/plan` | مشاهده/تغییر پلن |
| `/subscribe` | عضویت |
| `/unsubscribe` | لغو عضویت |

### دستورات ادمین

| دستور | توضیح |
|---|---|
| `/admin` | باز کردن پنل ادمین (interactive) |
| `/grant <user_id> <PLAN> [days]` | اختصاص پلن (مثل `/grant 123 PRO 30`) |
| `/revoke <user_id>` | حذف کامل اشتراک |
| `/userinfo <user_id>` | نمایش اطلاعات پلن یک کاربر |
| `/plans` | نمایش پلن‌ها + آمار ادمین |

### منوی شیشه‌ای (Reply Keyboard)

```
┌─────────────────────┬─────────────────────┐
│  📋 هشدارهای من      │  💲 قیمت لحظه‌ای      │
├─────────────────────┼─────────────────────┤
│  ➕ افزودن هشدار     │  🗑 حذف هشدار        │
├─────────────────────┼─────────────────────┤
│  💎 پلن‌ها            │  ℹ️ راهنما           │
├─────────────────────┼─────────────────────┤
│                     │  💼 پنل ادمین*       │
└─────────────────────┴─────────────────────┘
* فقط برای ادمین
```

---

## 💎 پلن‌های اشتراک

### فلوی خرید (امن)

1. کاربر روی `💎 پلن حرفه‌ای — 💳 خرید` کلیک می‌کند
2. **ربات هیچ تغییری در پلن نمی‌دهد** — فقط اطلاعات پرداخت نشان می‌دهد
3. **درخواست به ادمین(ها) ارسال می‌شود** با دکمه‌های ✅ / ❌
4. کاربر مبلغ را به `ADMIN_CONTACT` واریز می‌کند و رسید می‌فرستد
5. **ادمین تایید می‌کند** → پلن خودکار فعال می‌شود + به کاربر اطلاع داده می‌شود
6. یا **ادمین رد می‌کند** → کاربر مطلع می‌شود

### Auto-Demotion

- اگر پلن PRO/VIP منقضی شود:
  - در `/plan` → خودکار به FREE تنزل می‌یابد
  - در `/userinfo` → خودکار به FREE تنزل می‌یابد
  - هر شب ساعت `00:05` → همه کاربران منقضی یکجا تنزل می‌یابند
  - در استارت بات → یک‌بار cleanup کامل

---

## 👑 پنل ادمین

بعد از تنظیم `ADMIN_IDS` در `.env` و ری‌استارت:

1. در تلگرام `/admin` بفرست
2. پنل زیر نمایش داده می‌شود:

```
💼 پنل ادمین

📊 آمار کاربران:
  🆓 FREE: 30
  ⭐ PRO: 15
  💎 VIP: 5
  ⚠️ منقضی: 2
  👥 مجموع: 52

📩 درخواست‌های در انتظار: 2

[📩 درخواست‌های خرید (2)]
[📊 آمار] [👥 لیست کاربران]
[🔍 جستجوی کاربر]
[↩️ بستن]
```

---

## 🐳 داکر

### با `docker compose` (توصیه‌شده)

```bash
docker compose up -d
docker compose logs -f
docker compose restart
```

### با `docker run`

```bash
docker build -t crypto-alert-bot .
docker run -d \
  --name crypto-alert-bot \
  --restart unless-stopped \
  --env-file .env \
  -v $(pwd)/data:/app/data \
  crypto-alert-bot
```

---

## 🧠 معماری

### جریان داده

```
┌─────────────────────────────────────────────────────┐
│                  Telegram Bot API                    │
└──────────────────────┬──────────────────────────────┘
                       │
                       ▼
┌─────────────────────────────────────────────────────┐
│            Application (PTB)                         │
│  ┌──────────────┐  ┌──────────────┐                 │
│  │  Handlers    │  │  Callbacks   │                 │
│  │  (commands)  │  │ (buttons)    │                 │
│  └──────┬───────┘  └──────┬───────┘                 │
└─────────┼──────────────────┼────────────────────────┘
          │                  │
          ▼                  ▼
┌─────────────────────────────────────────────────────┐
│            Domain Layer (bot/*.py)                   │
│  alerts  │  subscriptions  │  admin                  │
└────┬─────────────┬──────────────┬───────────────────┘
     │             │              │
     ▼             ▼              ▼
┌─────────────────────────────────────────────────────┐
│         Storage (in-memory cache + JSON)             │
│  load_json / save_json  (per-file lock)              │
└─────────────────────────────────────────────────────┘
                          │
                          ▼
                  ┌──────────────────┐
                  │  data/*.json     │
                  └──────────────────┘
```

### Background Tasks

| Task | Interval | کار |
|---|---|---|
| `check_alerts_loop` | ۶۰s | چک قیمت همه هشدارها |
| `_demote_expired_job` | روزانه ۰۰:۰۵ | تنزل پلن‌های منقضی |

### Optimizations

- **Connection Pool** مشترک برای همه درخواست‌های HTTP (۱۵ connection همزمان)
- **In-memory cache** برای فایل‌های JSON (پس از اولین load، I/O صفر)
- **Per-file lock** به جای global (parallel reads)
- **Parallel price fetching** با `asyncio.gather` در رندر alert list و چک loop
- **Skip empty saves** در alert loop (اگه تغییری نکرد، فایل save نمیشه)

---

## 🔧 سفارشی‌سازی

### تغییر قیمت/محدودیت پلن‌ها

در [`bot/config.py`](bot/config.py):

```python
PLANS: Dict[str, Plan] = {
    "FREE": Plan(price_toman=0, max_alerts=3, max_charts_per_day=2, ...),
    "PRO": Plan(price_toman=250_000, duration_days=30, max_alerts=8, ...),
    "VIP": Plan(price_toman=750_000, duration_days=30, max_alerts=-1, ...),
}
```

---

## 🛠 عیب‌یابی

| مشکل | علت | راه‌حل |
|---|---|---|
| `Conflict: terminated by other getUpdates` | دو نمونه از بات در حال اجراست | نمونه قبلی را ببندید: `pkill -9 -f 'python.*main.py'` |
| `401 Unauthorized` | توکن اشتباه | توکن را از @BotFather دوباره بگیرید |
| `ImportError: zoneinfo` | Python < 3.10 | به Python 3.10+ ارتقا دهید |
| چارت نمایش داده نمی‌شود | `CHART_API_KEY` خالی | از [chart-img.com](https://chart-img.com) کلید بگیرید |
| `Permission denied: data/` | مالکیت فایل‌ها | `sudo chown -R crypto-alert:crypto-alert /opt/crypto-alert` |
| بات بعد از ریبوت بالا نمیاد | سرویس enable نشده | `sudo systemctl enable crypto-alert` |

---

## 🧪 تست

### تست قیمت

```bash
python -c "
import asyncio
from bot.prices import get_price_info

async def main():
    for sym in ['BTCUSDT', 'ETHUSDT', 'BTC.D']:
        info = await get_price_info(sym)
        if info:
            print(f'{sym}: {info[\"price\"]} ({info[\"market\"]})')

asyncio.run(main())
"
```

### تست health

```bash
curl -sf https://api.telegram.org/bot${TELEGRAM_TOKEN}/getMe | python -m json.tool
```

---

## 🤝 مشارکت

1. Fork کنید
2. برنچ بسازید (`git checkout -b feature/amazing`)
3. تغییرات را commit کنید (`git commit -m 'feat: add amazing feature'`)
4. Push کنید (`git push origin feature/amazing`)
5. Pull Request باز کنید

---

## 📜 مجوز

این پروژه تحت مجوز **MIT** منتشر شده است. برای جزئیات [`LICENSE`](LICENSE) را ببینید.

---

<p align="center">
  ساخته‌شده با ❤️ برای جامعه کریپتو فارسی
</p>
