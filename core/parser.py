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
from telethon.errors import FloodWaitError
from datetime import timedelta
logger = setup_logger(  )


async def initialize_blacklist():
    """
    Initialize the blacklist with default patterns if they don't exist in DB
    """
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


async def parse_channel(channel_name, months=None, all_time=False, limit=10):
    """
    Parse channel posts with different time periods, including forwarded messages
    
    Args:
        channel_name (str): Channel name or link
        months (int): Number of months to parse (None by default)
        all_time (bool): Parse all posts if True (False by default)
        limit (int): Limit of posts to parse if months and all_time are False
    """
    channel = channel_name.split("/")[-1] if "/" in channel_name else channel_name
    
    try:
        chat = await telegram_client.get_chat(channel)
        logger.info(f"get chat {chat.title}, id - {chat.id}")
        saved_count = 0
        
        async def process_message(message):
            nonlocal saved_count
            # Save original message
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

            # Handle forwarded message
            if message.forward_from_chat or message.forward_from:
                forward_text = message.text
                forward_link = message.link
                forward_date = message.forward_date or message.date
                
                # Get forwarded channel info if available
                forward_channel = None
                if message.forward_from_chat:
                    forward_channel = f"https://t.me/{message.forward_from_chat.username or message.forward_from_chat.id}"
                
                saved = await save_post(
                    check_date=datetime.now(),
                    post_date=forward_date,
                    channel_link=forward_channel or f"https://t.me/{channel_name}",
                    post_link=forward_link,
                    post_text=forward_text,
                    user_requested=0,
                    is_forwarded=True  # Add flag to indicate forwarded message
                )
                if saved:
                    logger.info(
                        LOG_DB["save_post"].format(link=forward_link, date=forward_date)
                    )
                    saved_count += 1

        if all_time:
            # Parse all posts with delay
            async for message in telegram_client.get_chat_history(chat.id):
                await asyncio.sleep(0.5)  # Delay between requests
                await process_message(message)
                    
        elif months:
            # Parse posts for last N months
            date_from = datetime.now() - timedelta(days=30*months)
            async for message in telegram_client.get_chat_history(chat.id):
                if message.date < date_from:
                    break
                await process_message(message)
                    
        else:
            # Parse limited number of posts
            async for message in telegram_client.get_chat_history(chat.id, limit=limit):
                await process_message(message)
                    
        return saved_count

    except FloodWaitError as e:
        logger.error(f"FloodWaitError: waiting for {e.seconds} seconds")
        await asyncio.sleep(e.seconds)
        return await parse_channel(channel_name, months, all_time, limit)
        
    except Exception as e:
        logger.error(LOG_DB["parse_error"].format(e=e))
        return 0
async def parse_all_active_channels(months=None, all_time=False, limit_per_channel=10):
    """
    Parse all active channels with specified parameters
    
    Args:
        months (int): Number of months to parse (None by default)
        all_time (bool): Parse all posts if True (False by default)
        limit_per_channel (int): Limit of posts per channel if months and all_time are False
    """
    logger.info(LOG_DB["start_parse"])
    total_saved = 0
    channels = await get_active_channels()
    
    for channel in channels:
        try:
            logger.info(LOG_DB["process"].format(channel=channel))
            
            # Добавляем обработку различных режимов парсинга
            if all_time:
                logger.info(f"Parsing all posts from channel: {channel}")
                saved = await parse_channel(channel, all_time=True)
            elif months:
                logger.info(f"Parsing last {months} months from channel: {channel}")
                saved = await parse_channel(channel, months=months)
            else:
                logger.info(f"Parsing last {limit_per_channel} posts from channel: {channel}")
                saved = await parse_channel(channel, limit=limit_per_channel)
                
            total_saved += saved
            
            # Добавляем адаптивную задержку между каналами
            delay = 5 if all_time else 2  # Увеличенная задержка при парсинге всех постов
            logger.info(f"Waiting {delay} seconds before next channel...")
            await asyncio.sleep(delay)
            
        except FloodWaitError as e:
            logger.error(f"FloodWaitError for channel {channel}: waiting {e.seconds} seconds")
            await asyncio.sleep(e.seconds)
            # Можно добавить повторную попытку парсинга этого канала
            try:
                saved = await parse_channel(channel, months=months, all_time=all_time, limit=limit_per_channel)
                total_saved += saved
            except Exception as retry_e:
                logger.error(f"Retry failed for channel {channel}: {retry_e}")
                continue
                
        except Exception as e:
            logger.error(LOG_DB["parse_error"].format(e=e))
            logger.error(f"Failed channel: {channel}, error: {str(e)}")
            continue
            
    logger.info(f"Total posts saved: {total_saved}")
    return total_saved