import asyncio
import logging
from datetime import datetime
from telethon import TelegramClient
from database.db import save_post, get_active_channels, get_last_post_id, add_to_blacklist, is_blacklisted, \
    deactivate_channel, get_cursor
from config import TELEGRAM_API_ID, TELEGRAM_API_HASH, CHANNELS_TO_PARSE

logging.basicConfig(level=logging.INFO, filename='log.py', filemode='w')

"""
todo: сделать обработку ошибок
todo: написать логирование
todo: написать кнопку вывода
"""

# Автодобавление распространенных невалидных шаблонов
DEFAULT_BLACKLIST_PATTERNS = [
    ("admin", "Служебный псевдоним"),
    ("support", "Служебный псевдоним"),
    # ("bot", "Служебный псевдоним"),
    ("telegram", "Официальные каналы"),
    ("[a-z]{1,3}", "Слишком короткие имена")
]


async def initialize_blacklist():
    """Заполняет черный список базовыми шаблонами, если они ещё не добавлены."""
    for pattern, reason in DEFAULT_BLACKLIST_PATTERNS:
        try:
            exists = await is_blacklisted(pattern, check_pattern=True)
            if not exists:
                await add_to_blacklist(pattern, reason)
                logging.info(f"✅ Шаблон '{pattern}' добавлен в черный список: {reason}")
            else:
                logging.debug(f"ℹ Шаблон '{pattern}' уже в черном списке")
        except Exception as e:
            logging.error(f"❌ Ошибка при добавлении шаблона '{pattern}': {e}")


async def parse_channel(client: TelegramClient, channel_name: str, limit: int = 10) -> int:
    """
    Парсит указанный Telegram-канал через переданный клиентский объект.

    :param client: Активный экземпляр TelegramClient (уже авторизованный)
    :param channel_name: Название/ссылка на канал
    :param limit: Максимальное количество постов для парсинга
    :return: Количество успешно сохранённых постов
    """
    channel_link = f"https://t.me/ {channel_name}"

    logging.info(f"🔍 Начинаем парсинг канала: {channel_name}")
    print(f"🔍 Начинаем парсинг канала: {channel_name}")

    # Проверяем, находится ли канал или имя пользователя в черном списке
    if await is_blacklisted(channel_name):
        logging.warning(f"⏭ Канал '{channel_name}' в черном списке. Пропускаем.")
        return 0

    try:
        entity = await client.get_entity(channel_name)
    except (ValueError, TypeError) as e:
        error_msg = f"❌ Не удалось получить сущность канала '{channel_name}': {e}"
        logging.warning(error_msg)
        await deactivate_channel(channel_link, str(e))
        return 0
    except Exception as e:
        logging.exception(f"⚠️ Неожиданная ошибка при получении сущности '{channel_name}': {e}")
        return 0

    base_link = f"https://t.me/ {entity.username}" if hasattr(entity, 'username') else channel_link
    saved_count = 0

    try:
        async for message in client.iter_messages(entity, limit=limit):
            if not message.text and not message.media:
                logging.debug(f"📎 Пропущено сообщение без текста/медиа: {message.id}")
                continue

            post_link = f"{base_link}/{message.id}"
            try:
                saved = await save_post(
                    check_date=datetime.now(),
                    post_date=message.date,
                    channel_link=base_link,
                    post_link=post_link,
                    post_text=message.text,
                    user_requested=0
                )
                if saved:
                    saved_count += 1
                    logging.debug(f"✅ Сохранен пост {message.id}")
            except Exception as e:
                logging.error(f"❌ Ошибка сохранения поста {message.id}: {e}", exc_info=True)

        # Обновляем историю проверок
        with get_cursor() as cur:
            await cur.execute(
                """INSERT OR REPLACE INTO channel_history 
                   (channel_link, status, last_checked) 
                   VALUES (?, 'active', datetime('now'))""",
                (channel_link,)
            )
            cur.connection.commit()
        logging.info(f"📥 Канал '{channel_name}' обработан. Сохранено постов: {saved_count}")
        return saved_count

    except Exception as e:
        logging.error(f"🔥 Критическая ошибка при парсинге канала '{channel_name}': {e}", exc_info=True)
        return 0
    пше 

async def parse_all_active_channels(limit_per_channel: int = 10) -> int:
    """
    Парсинг всех активных каналов с гарантированным возвратом int
    :return: Общее количество сохраненных постов
    """
    channels = await get_active_channels()
    if not channels:
        print("ℹ Нет активных каналов для парсинга")
        return 0

    total_saved = 0
    for channel in channels:
        try:
            saved = await parse_channel(channel, limit=limit_per_channel)
            total_saved += saved  # Теперь saved всегда int
            print(f"ℹ [{channel}] Обработано постов: {saved}")
            await asyncio.sleep(1)  # Задержка между каналами
        except Exception as e:
            print(f"❌ Ошибка обработки канала {channel}: {e}")
            continue

    print(f"✅ Всего сохранено постов: {total_saved}")
    return total_saved


# todo: написать функцию для удаления канала из тбота

async def start_scheduled_parsing(interval: int = 3600, limit: int = 50):
    """Фоновая задача парсинга с улучшенным логированием"""
    while True:
        try:
            print(f"\n{datetime.now().isoformat()} 🔍 Начало планового парсинга")

            # Перед парсингом проверяем черный список
            channels = await get_active_channels()
            valid_channels = [
                ch for ch in channels
                if not await is_blacklisted(ch)
            ]

            if not valid_channels:
                print("ℹ Нет активных каналов, пропускаем цикл")
                await asyncio.sleep(interval)
                continue

            saved_total = 0
            for channel in valid_channels:
                channel_name = channel.split('/')[-1]
                saved = await parse_channel(channel_name, limit)
                saved_total += saved
                await asyncio.sleep(1)  # Задержка между каналами

            print(f"✅ Цикл завершен. Сохранено постов: {saved_total}")
            print(f"⏳ Следующий парсинг через {interval // 60} минут")

        except Exception as e:
            print(f"🔥 Критическая ошибка в планировщике: {repr(e)}")
            await asyncio.sleep(300)  # Короткая пауза при ошибке
        else:
            await asyncio.sleep(interval)


async def start_parsing(interval=3600):
    while True:
        for channel in CHANNELS_TO_PARSE:
            try:
                await parse_channel(channel)
            except Exception as e:
                print(f"Error parsing {channel}: {e}")
        await asyncio.sleep(interval)
