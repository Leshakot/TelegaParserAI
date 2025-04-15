import asyncio
import re
from telethon import TelegramClient
from database.db import save_new_channel
from config import TELEGRAM_API_ID, TELEGRAM_API_HASH

CHANNEL_REGEX = r"(?:https?://)?t\.me/([a-zA-Z0-9_]{5,32})"

async def find_channels_in_post(text):
    return re.findall(CHANNEL_REGEX, text)

async def start_channel_finder(interval=1800):
    async with TelegramClient('session_name', TELEGRAM_API_ID, TELEGRAM_API_HASH) as client:
        while True:
            # Здесь логика поиска новых каналов
            # Например, проверка последних постов в мониторимых каналах
            await asyncio.sleep(interval)