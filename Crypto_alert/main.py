import asyncio
import requests
from telegram import Bot


# مشخصات
TELEGRAM_TOKEN = "8158643934:AAEGKx9DGpo9K5ih1BVGIyNVU6HQmA81dd8"
CHAT_ID = "120223427"


alerts = [
    {"symbol": "BTCUSDT", "target": 60000},
    {"symbol": "ETHUSDT", "target": 3500},
]

bot = Bot(token=TELEGRAM_TOKEN)
sent_alerts = set()


def get_price(symbol):
    url = f"https://api.binance.com/api/v3/ticker/price?symbol={symbol}"
    try:
        response = requests.get(url)
        print(response)
        response.raise_for_status()
        print(response.json())
        
        return float(response.json()["price"])
    except:
        return None

async def send_start_message():
    await bot.send_message(chat_id=CHAT_ID, text="شروع بررسی قیمت‌ها...")


async def check_alerts():
    while True:
        for alert in alerts:
            price = get_price(alert["symbol"])
            if price is None:
                continue
            if price >= alert["target"] and alert["symbol"] not in sent_alerts:
                message = (
                    f"🎯 {alert['symbol']} رسید به {price} (هدف: {alert['target']})"
                )
                await bot.send_message(chat_id=CHAT_ID, text=message)
                sent_alerts.add(alert["symbol"])
        await asyncio.sleep(15)


async def main():
    await send_start_message()
    await check_alerts()


if __name__ == "__main__":
    asyncio.run(main())
