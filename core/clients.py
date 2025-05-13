import asyncio
from telethon import TelegramClient
from config import TELEGRAM_API_ID, TELEGRAM_API_HASH

telegram_client = None  # Глобальная переменная для клиента


async def init_telegram_client(bot_message=None):
    """
    Инициализирует Telethon клиент. Если сессия недействительна, запросит телефон и код.
    """
    global telegram_client

    telegram_client = TelegramClient(
        'user_session',
        api_id=TELEGRAM_API_ID,
        api_hash=TELEGRAM_API_HASH
    )

    if not await telegram_client.is_user_authorized():
        await telegram_client.connect()

        if not await telegram_client.is_user_authorized():
            print("⚠️ Требуется авторизация...")
            if bot_message:
                await bot_message.answer("📞 Введите ваш номер телефона:")

            phone = input("Введите номер телефона: ")
            await telegram_client.send_code_request(phone)
            code = input("Введите код из Telegram: ")

            try:
                await telegram_client.sign_in(phone, code)
            except Exception as e:
                print(f"❌ Ошибка авторизации: {e}")
                if bot_message:
                    await bot_message.answer("❌ Не удалось войти. Проверьте код.")
                return False

    print("✅ Telethon клиент успешно авторизован")
    if bot_message:
        await bot_message.answer("✅ Telethon клиент подключен")
    return True