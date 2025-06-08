from telethon import TelegramClient
from config import TELEGRAM_API_ID, TELEGRAM_API_HASH, TELEGRAM_PHONE

# Глобальная переменная для клиента
telegram_client = TelegramClient(
    "user_session", TELEGRAM_API_ID, TELEGRAM_API_HASH, auto_reconnect=True
)


async def init_telegram_client(bot_message=None):
    """
    Инициализирует Telethon клиент. Если сессия недействительна, запросит телефон и код.
    """
    if not telegram_client.is_connected():
        await telegram_client.connect()

    if not await telegram_client.is_user_authorized():
        print("⚠️ Требуется авторизация...")
        # if bot_message:
        # await bot_message.answer("📞 Введите ваш номер телефона:")

        phone = TELEGRAM_PHONE
        await telegram_client.send_code_request(phone)
        code = input("✉️ Введите код из Telegram: ")

        try:
            await telegram_client.sign_in(phone, code)
            print("✅ Авторизован в Telegram")
            if bot_message:
                await bot_message.answer("✅ Авторизован в Telegram")
            return True
        except Exception as e:
            print(f"❌ Ошибка авторизации: {e}")
            if bot_message:
                await bot_message.answer("❌ Не удалось войти. Проверьте код.")
            return False

    return True


async def ensure_telegram_client_connected():
    print("ensure_telegram_client_connected")
    if not telegram_client.is_connected():
        print("try to connect")
        await telegram_client.connect()
    if not await telegram_client.is_user_authorized():
        print("try to start client")
        await telegram_client.start()
        if not telegram_client.is_user_authorized():
            return False
    return True
