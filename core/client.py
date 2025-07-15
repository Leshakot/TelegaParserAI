from pyrogram import Client
from config import TELEGRAM_API_ID, TELEGRAM_API_HASH


telegram_client = Client(
    "data/user_session",
    TELEGRAM_API_ID,
    TELEGRAM_API_HASH,
)
