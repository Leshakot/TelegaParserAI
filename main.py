import asyncio
import logging
from aiogram import Bot, Dispatcher
from telethon import TelegramClient

# Твои модули
from database.db import ensure_db_initialized, initialize_blacklist
from core.bot_controller import setup_bot_handlers
from core.parser import start_scheduled_parsing
from config import TELEGRAM_API_ID, TELEGRAM_API_HASH, TELEGRAM_BOT_TOKEN

# Настройка логирования
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)

# Глобальный клиент Telethon
from core.clients import telegram_client


async def main():
    logger.info("🚀 Запуск бота и инициализация систем...")

    # 1. Проверяем и создаём БД
    await ensure_db_initialized()
    logger.info("🛠 База данных инициализирована")

    # 2. Инициализируем чёрный список
    await initialize_blacklist()
    logger.info("🚫 Чёрный список загружен")

    # 3. Авторизуемся как пользователь Telegram
    await telegram_client.start()
    if not await telegram_client.is_user_authorized():
        logger.warning("⚠️ Требуется авторизация через телефон и код")
        phone = input("📞 Введите номер телефона: ")
        await telegram_client.send_code_request(phone)
        code = input("✉️ Введите код из Telegram: ")
        try:
            await telegram_client.sign_in(phone, code)
        except Exception as e:
            logger.error(f"❌ Ошибка авторизации: {e}")
            return

    logger.info("✅ Успешно авторизован в Telegram")

    # 4. Инициализируем бота
    bot = Bot(token=TELEGRAM_BOT_TOKEN)
    dp = Dispatcher()

    # 5. Регистрируем обработчики
    setup_bot_handlers(dp)

    # 6. Запуск фоновой задачи парсинга
    asyncio.create_task(start_scheduled_parsing(client=telegram_client))

    # 7. Запуск бота
    logger.info("🟢 Бот запущен и готов к работе")
    try:
        await dp.start_polling(bot)
    finally:
        await bot.session.close()
        await telegram_client.disconnect()
        logger.info("🛑 Бот и клиент Telegram остановлены")


if __name__ == "__main__":
    asyncio.run(main())