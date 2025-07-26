import asyncio
import requests
from telegram import Bot
import numpy as np

# مشخصات
TELEGRAM_TOKEN = "8158643934:AAEGKx9DGpo9K5ih1BVGIyNVU6HQmA81dd8"
CHAT_ID = "120223427"


alerts = [
    {'ID':1,"symbol": "BTCUSDT", "target": 60000,'Goal':'D'},
    {'ID':2,"symbol": "ETHUSDT", "target": 3500,'Goal':'D'},
    {'ID':3,"symbol": "ETHUSDT", "target": 350,'Goal':'U'},
]

bot = Bot(token=TELEGRAM_TOKEN)
sent_alerts = set()


def get_price():
    url = f"https://api.binance.com/api/v3/ticker/price"
    try:
        response = requests.get(url)
        response.raise_for_status()
        response = np.array(response.json()) 
        return response
    except:
        return None

async def send_start_message():
    await bot.send_message(chat_id=CHAT_ID, text="شروع بررسی قیمت‌ها...")


async def check_alerts():
    while True:
        data= get_price()
        for alert in alerts:
            for item in data:
                if item['symbol'] == alert['symbol']:
                    price = float(item['price'])
                    if alert['Goal']=='D':
                        if price >= alert["target"] and alert["ID"] not in sent_alerts:
                            message = (
                                f"🎯 {alert['symbol']} رسید به {price} (هدف: {alert['target']})"
                            )
                            await bot.send_message(chat_id=CHAT_ID, text=message)
                            sent_alerts.add(alert["ID"])
                    elif alert['Goal']=='U':
                        if price <= alert["target"] and alert["ID"] not in sent_alerts:
                            message = (
                                f"🎯 {alert['symbol']} رسید به {price} (هدف: {alert['target']})"
                            )
                            await bot.send_message(chat_id=CHAT_ID, text=message)
                            sent_alerts.add(alert["ID"])
        await asyncio.sleep(15)


async def main():
    await send_start_message()
    await check_alerts()


if __name__ == "__main__":
    asyncio.run(main())




# import asyncio
# import requests
# from telegram import Bot
# from flask import Flask
# import threading

# TELEGRAM_TOKEN = "8158643934:AAEGKx9DGpo9K5ih1BVGIyNVU6HQmA81dd8"
# CHAT_ID = "120223427"

# # اهداف قیمت
# alerts = [
#     {"id": "bitcoin", "symbol": "BTC", "target": 60000},
#     {"id": "ethereum", "symbol": "ETH", "target": 3500},
# ]

# bot = Bot(token=TELEGRAM_TOKEN)
# sent_alerts = set()

# # سرور Flask
# app = Flask('')
# @app.route('/')
# def home():
#     return "Bot is alive."

# def run_web():
#     app.run(host='0.0.0.0', port=8080)

# threading.Thread(target=run_web).start()

# # گرفتن قیمت همه کوین‌ها با یک درخواست
# def get_prices(coin_ids):
#     ids = ",".join(coin_ids)
#     url = f"https://api.coingecko.com/api/v3/simple/price?ids={ids}&vs_currencies=usd"
#     try:
#         response = requests.get(url)
#         response.raise_for_status()
#         return response.json()
#     except Exception as e:
#         print(f"❌ خطا در گرفتن قیمت‌ها: {e}")
#         return {}

# # چک کردن و ارسال هشدار
# async def check_alerts():
#     coin_ids = [a["id"] for a in alerts]
#     while True:
#         prices = get_prices(coin_ids)
#         for alert in alerts:
#             price = prices.get(alert["id"], {}).get("usd")
#             if price is None:
#                 print(f"⚠️ قیمت {alert['symbol']} دریافت نشد.")
#                 continue
#             print(f"{alert['symbol']} → {price} | هدف: {alert['target']}")
#             if price >= alert["target"] and alert["symbol"] not in sent_alerts:
#                 message = f"🎯 {alert['symbol']} رسید به {price} دلار (هدف: {alert['target']})"
#                 await bot.send_message(chat_id=CHAT_ID, text=message)
#                 sent_alerts.add(alert["symbol"])
#         await asyncio.sleep(30)  # فاصله زمانی بیشتر برای جلوگیری از محدودیت

# # پیام شروع
# async def send_start_message():
#     await bot.send_message(chat_id=CHAT_ID, text="✅ بررسی قیمت رمزارزها شروع شد.")

# # اجرای برنامه
# async def main():
#     await send_start_message()
#     await check_alerts()

# asyncio.run(main())
