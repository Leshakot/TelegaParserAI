import asyncio
import logging
from aiogram import Bot, Dispatcher
from aiogram.fsm.storage.memory import MemoryStorage

from core.bot_controller import setup_bot_handlers
from config import TELEGRAM_BOT_TOKEN
from core.client import telegram_client

from utils.logger import setup_logger


logger = setup_logger()
logging.getLogger("pyrogram").setLevel(logging.WARNING)


async def on_start_up():
    await telegram_client.start()


async def on_shutdown():
    await telegram_client.stop()


async def main():
    bot = Bot(token=TELEGRAM_BOT_TOKEN)
    dp = Dispatcher(storage=MemoryStorage())
    setup_bot_handlers(dp)

    dp.startup.register(on_start_up)
    dp.shutdown.register(on_shutdown)

    await bot.delete_webhook(drop_pending_updates=True)
    await dp.start_polling(bot)


if __name__ == "__main__":
    asyncio.run(main())
