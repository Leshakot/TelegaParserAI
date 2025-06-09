import asyncio
from datetime import datetime

from core.client import telegram_client
from database.db_commands import (
    save_post,
    get_active_channels,
    add_to_blacklist,
    is_blacklisted,
)
from utils.logger import setup_logger
from constants.logger import LOG_DB
from constants.db_constants import DEFAULT_PATTERNS


logger = setup_logger()


async def initialize_blacklist():
    """Заполняет черный список базовыми шаблонами, если их ещё нет в БД."""
    for pattern, reason in DEFAULT_PATTERNS:
        try:
            exists = await is_blacklisted(pattern, check_pattern=True)
            if not exists:
                await add_to_blacklist(pattern, reason)
                logger.info(
                    LOG_DB["pattern_save"].format(pattern=pattern, reason=reason)
                )
            else:
                logger.debug(LOG_DB["in_blacklist"].format(pattern=pattern))
        except Exception as e:
            logger.error(LOG_DB["patter_error"].format(pattern=pattern, e=e))


async def parse_channel(channel_name, limit=10):
    channel = channel_name.split("/")[-1] if "/" in channel_name else channel_name
    chat = await telegram_client.get_chat(channel)
    logger.info(f"get chat {chat.title}, id - {chat.id}")
    saved_count = 0
    try:
        async for message in telegram_client.get_chat_history(chat.id, limit=limit):
            saved = await save_post(
                check_date=datetime.now(),
                post_date=message.date,
                channel_link=f"https://t.me/{channel_name}",
                post_link=message.link,
                post_text=message.text,
                user_requested=0,
            )
            if saved:
                logger.info(
                    LOG_DB["save_post"].format(link=message.link, date=message.date)
                )
                saved_count += 1
        return saved_count
    except Exception as e:
        logger.error(LOG_DB["parse_error"].format(e=e))
        return 0


async def parse_all_active_channels(limit_per_channel=10):
    logger.info(LOG_DB["start_parse"])
    total_saved = 0
    channels = await get_active_channels()
    for channel in channels:
        try:
            logger.info(LOG_DB["process"].format(channel=channel))
            saved = await parse_channel(channel, limit=limit_per_channel)
            total_saved += saved
            await asyncio.sleep(2)
        except Exception as e:
            logger.error(LOG_DB["parse_error"].format(e=e))
            continue
    return total_saved
