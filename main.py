import asyncio
import logging
from aiogram import Bot, Dispatcher
from aiogram.fsm.storage.memory import MemoryStorage

# Твои модули
from database.db_commands import initialize_blacklist
from core.bot_controller import setup_bot_handlers
from core.parser import start_scheduled_parsing
from config import TELEGRAM_BOT_TOKEN, TELEGRAM_API_ID, TELEGRAM_API_HASH

# Настройка логирования
logging.basicConfig(
    level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)


async def main():
    logger.info("🚀 Запуск бота и инициализация систем...")

    # 1. Проверяем и создаём БД
    # await ensure_db_initialized()
    # logger.info("🛠 База данных инициализирована")

    # 2. Инициализируем чёрный список
    await initialize_blacklist()
    logger.info("🚫 Чёрный список загружен")

    # 3. Создаём клиента Telegram
    from core.clients import telegram_client  # <-- должен быть создан заранее

    # 4. Подключаемся к Telegram
    logger.info("📞 Подключение к Telegram...")
    try:
        await telegram_client.connect()
    except Exception as e:
        logger.critical(f"🔴 Не удалось подключиться к Telegram: {e}")
        return

    # 5. Проверяем авторизацию
    if not await telegram_client.is_user_authorized():
        logger.warning("⚠️ Требуется авторизация через телефон и код")
        phone = input("📞 Введите номер телефона: ")
        await telegram_client.send_code_request(phone)
        code = input("✉️ Введите код из Telegram: ")

        try:
            await telegram_client.sign_in(phone, code)
            logger.info("✅ Авторизован в Telegram")
        except Exception as e:
            logger.error(f"❌ Ошибка авторизации: {e}")
            return

    # 6. Инициализируем бота
    bot = Bot(token=TELEGRAM_BOT_TOKEN)
    dp = Dispatcher(storage=MemoryStorage())

    # 7. Регистрируем обработчики
    setup_bot_handlers(dp)

    # 8. Запуск фоновой задачи парсинга
    # asyncio.create_task(start_scheduled_parsing(client=telegram_client))

    # 9. Запуск бота
    logger.info("🟢 Бот запущен и готов к работе")
    # try:
    #     await dp.start_polling(bot)
    #     logger.info("🟢 Бот запущен и готов к работе")
    # finally:
    #     await bot.session.close()
    #     await telegram_client.disconnect()
    #     logger.info("🛑 Бот и клиент Telegram остановлены")
    try:
        await bot.delete_webhook(drop_pending_updates=True)
        await dp.start_polling(bot)
    finally:
        await telegram_client.disconnect()


if __name__ == "__main__":
    asyncio.run(main())
