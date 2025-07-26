import asyncio
import requests
from telegram import Bot
import numpy as np

# مشخصات
TELEGRAM_TOKEN = "xxxxxxxxxxxxxxxxxxxxxxxxxxx"
CHAT_ID = "xxxxxxxxxxx"


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
