import asyncio
from aiogram import Bot, Dispatcher
from database.db import ensure_db_initialized
from core.bot_controller import setup_bot_handlers
from core.parser import start_scheduled_parsing, initialize_blacklist
from config import TELEGRAM_BOT_TOKEN


async def main():
    # Инициализация и проверка БД
    await ensure_db_initialized()
    await initialize_blacklist()

    # Инициализация бота
    bot = Bot(token=TELEGRAM_BOT_TOKEN)
    dp = Dispatcher()

    # Настройка обработчиков
    setup_bot_handlers(dp)

    # Запуск фоновых задач
    # asyncio.create_task(start_scheduled_parsing())

    try:
        await dp.start_polling(bot)
    finally:
        await bot.session.close()


if __name__ == "__main__":
    asyncio.run(main())
