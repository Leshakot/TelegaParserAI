import asyncio
from datetime import datetime
from telethon import TelegramClient
from database.db import save_post, get_active_channels, get_last_post_id, add_to_blacklist, is_blacklisted, deactivate_channel, get_cursor
from config import TELEGRAM_API_ID, TELEGRAM_API_HASH, CHANNELS_TO_PARSE


# Автодобавление распространенных невалидных шаблонов
DEFAULT_BLACKLIST_PATTERNS = [
    ("admin", "Служебный псевдоним"),
    ("support", "Служебный псевдоним"),
    ("bot", "Служебный псевдоним"),
    ("telegram", "Официальные каналы"),
    ("[a-z]{1,3}", "Слишком короткие имена")
]

async def initialize_blacklist():
    """Заполняет черный список базовыми шаблонами"""
    for pattern, reason in DEFAULT_BLACKLIST_PATTERNS:
        await add_to_blacklist(pattern, reason)


async def parse_channel(channel_name: str, limit: int = 100) -> int:
    """Парсинг канала с обработкой ошибок и автоматической деактивацией"""
    channel_link = f"https://t.me/{channel_name}"

    # Проверка черного списка
    if await is_blacklisted(channel_link):
        print(f"⏭ Канал {channel_link} в черном списке, пропускаем")
        return 0

    try:
        async with TelegramClient('session_name', TELEGRAM_API_ID, TELEGRAM_API_HASH) as client:
            try:
                entity = await client.get_entity(channel_name)
            except (ValueError, TypeError) as e:
                error_msg = str(e)
                print(f"❌ Ошибка доступа к каналу {channel_link}: {error_msg}")
                await deactivate_channel(channel_link, error_msg)
                return 0

            base_link = f"https://t.me/{entity.username}" if hasattr(entity, 'username') else channel_link
            saved_count = 0

            async for message in client.iter_messages(entity, limit=limit):
                if not message.text:
                    continue

                saved = await save_post(
                    check_date=datetime.now(),
                    post_date=message.date,
                    channel_link=base_link,
                    post_link=f"{base_link}/{message.id}",
                    post_text=message.text,
                    user_requested=0
                )
                if saved:
                    saved_count += 1

            # Обновляем время последней проверки
            with get_cursor() as cur:
                cur.execute(
                    """INSERT OR REPLACE INTO channel_history 
                    (channel_link, status, last_checked) 
                    VALUES (?, 'active', datetime('now'))""",
                    (channel_link,)
                )

            return saved_count

    except Exception as e:
        error_msg = str(e)
        print(f"❌ Критическая ошибка парсинга {channel_link}: {error_msg}")
        await deactivate_channel(channel_link, error_msg)
        return 0


async def parse_all_active_channels(limit_per_channel: int = 50) -> int:
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
