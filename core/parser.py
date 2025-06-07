import asyncio
import logging
from datetime import datetime
from telethon import TelegramClient
from database.db_commands import (
    save_post,
    get_active_channels,
    add_to_blacklist,
    is_blacklisted,
    deactivate_channel,
    insert_repl_chan_history,
)

# Настройка логирования
logging.basicConfig(
    level=logging.INFO,
    # filename="parser.txt",
    # filemode="w",
    format="%(asctime)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger(__name__)

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
    ("[a-z]{1,3}", "Слишком короткие имена"),
]


async def initialize_blacklist():
    """Заполняет черный список базовыми шаблонами, если их ещё нет в БД."""
    for pattern, reason in DEFAULT_BLACKLIST_PATTERNS:
        try:
            exists = await is_blacklisted(pattern, check_pattern=True)
            if not exists:
                await add_to_blacklist(pattern, reason)
                logger.info(f"✅ Шаблон '{pattern}' добавлен в черный список: {reason}")
            else:
                logger.debug(f"ℹ Шаблон '{pattern}' уже в черном списке")
        except Exception as e:
            logger.error(f"❌ Ошибка при добавлении шаблона '{pattern}': {e}")


async def parse_channel(
    client: TelegramClient, channel_name: str, limit: int = 10
) -> int:
    """
    Парсит указанный Telegram-канал через переданный клиентский объект.

    :param client: Активный экземпляр TelegramClient (уже авторизованный)
    :param channel_name: Название/ссылка на канал
    :param limit: Максимальное количество постов для парсинга
    :return: Количество успешно сохранённых постов
    """
    channel_link = f"https://t.me/{channel_name.strip()}"
    logger.info(f"🔍 Начинаем парсинг канала: {channel_name}")
    print("in parse channel")
    # Проверяем, находится ли канал или имя пользователя в черном списке
    if await is_blacklisted(channel_name):
        logger.warning(f"⏭ Канал '{channel_name}' в черном списке. Пропускаем.")
        return 0

    try:
        print(f"try get parse channel {channel_name}")
        entity = await client.get_entity(channel_name)
    except (ValueError, TypeError) as e:
        error_msg = f"❌ Не удалось получить сущность канала '{channel_name}': {e}"
        logger.warning(error_msg)
        await deactivate_channel(channel_link, str(e))
        return 0
    except Exception as e:
        logger.exception(
            f"⚠️ Неожиданная ошибка при получении сущности '{channel_name}': {e}"
        )
        return 0

    base_link = (
        f"https://t.me/ {entity.username}"
        if hasattr(entity, "username")
        else channel_link
    )
    saved_count = 0
    print("NEXT STEP")
    try:
        async for message in client.iter_messages(entity, limit=limit):
            # print(message.text)
            print("iter for message")
            if not message.text and not message.media:
                logger.debug(f"📎 Пропущено сообщение без текста/медиа: {message.id}")
                continue

            post_link = f"{base_link}/{message.id}"
            try:
                saved = await save_post(
                    check_date=datetime.now(),
                    post_date=message.date,
                    channel_link=base_link,
                    post_link=post_link,
                    post_text=message.text,
                    user_requested=0,
                )
                if saved:
                    saved_count += 1
                    logger.debug(f"✅ Сохранен пост {message.id}")
            except Exception as e:
                logger.error(
                    f"❌ Ошибка сохранения поста {message.id}: {e}", exc_info=True
                )

        await insert_repl_chan_history(channel_link)
        logger.info(
            f"📥 Канал '{channel_name}' обработан. Сохранено постов: {saved_count}"
        )
        return saved_count

    except Exception as e:
        logger.error(
            f"🔥 Критическая ошибка при парсинге канала '{channel_name}': {e}",
            exc_info=True,
        )
        return 0


async def parse_all_active_channels(
    client: TelegramClient, limit_per_channel: int = 10
) -> int:
    """
    Парсит все активные каналы из базы данных через переданный TelegramClient.

    :param client: Активный экземпляр TelegramClient (уже авторизованный)
    :param limit_per_channel: Количество постов для парсинга на канал
    :return: Общее количество сохранённых постов
    """
    logger.info("🔄 Начинаем парсинг всех активных каналов")
    print("🔄 Начинаем парсинг всех активных каналов")

    channels = await get_active_channels()
    if not channels:
        logger.info("ℹ Нет активных каналов для парсинга")
        print("ℹ Нет активных каналов для парсинга")
        return 0

    total_saved = 0

    for channel in channels:
        try:
            # Извлекаем имя канала из ссылки, если нужно
            channel_name = channel.split("/")[-1] if "/" in channel else channel

            logger.info(f"📡 Обрабатываем канал: {channel_name}")
            print(f"📡 Обрабатываем канал: {channel_name}")

            saved = await parse_channel(client, channel_name, limit=limit_per_channel)
            total_saved += saved

            logger.info(f"📥 [{channel_name}] Сохранено постов: {saved}")
            print(f"📥 [{channel_name}] Сохранено постов: {saved}")

            await asyncio.sleep(2)  # Задержка между каналами для снижения нагрузки
        except Exception as e:
            logger.error(f"❌ Ошибка обработки канала {channel}: {e}", exc_info=True)
            print(f"❌ Ошибка обработки канала {channel}: {e}")
            continue

    logger.info(f"✅ Всего сохранено постов: {total_saved}")
    print(f"✅ Всего сохранено постов: {total_saved}")

    return total_saved


async def start_scheduled_parsing(
    client: TelegramClient, interval: int = 3600, limit_per_channel: int = 10
):
    """
    Фоновая задача парсинга с улучшенным логированием.
    """
    while True:
        try:
            logger.info(f"\n{datetime.now().isoformat()} 🔍 Начало планового парсинга")
            print(f"\n{datetime.now().isoformat()} 🔍 Начало планового парсинга")

            channels = await get_active_channels()
            if not channels:
                logger.info("ℹ Нет активных каналов, пропускаем цикл")
                print("ℹ Нет активных каналов, пропускаем цикл")
                await asyncio.sleep(interval)
                continue

            valid_channels = [ch for ch in channels if not await is_blacklisted(ch)]

            if not valid_channels:
                logger.info("ℹ Все каналы в черном списке, пропускаем цикл")
                print("ℹ Все каналы в черном списке, пропускаем цикл")
                await asyncio.sleep(interval)
                continue

            total_saved = 0
            for channel in valid_channels:
                channel_name = channel.split("/")[-1]
                print(channel_name)
                saved = await parse_channel(client, channel_name, limit_per_channel)
                total_saved += saved
                await asyncio.sleep(1)  # Задержка между каналами

            logger.info(f"✅ Цикл завершен. Сохранено постов: {total_saved}")
            print(f"✅ Цикл завершен. Сохранено постов: {total_saved}")
            logger.info(f"⏳ Следующий парсинг через {interval // 60} минут")
            print(f"⏳ Следующий парсинг через {interval // 60} минут")

        except Exception as e:
            logger.critical(
                f"🔥 Критическая ошибка в планировщике: {repr(e)}", exc_info=True
            )
            print(f"🔥 Критическая ошибка в планировщике: {repr(e)}")
            await asyncio.sleep(300)  # Короткая пауза при критической ошибке
        finally:
            await asyncio.sleep(interval)
