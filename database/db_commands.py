import logging
import csv
from datetime import datetime

from sqlalchemy import select, exists, and_
from sqlalchemy.exc import SQLAlchemyError

from database.database import get_db_session
from database.models import Post, Channel, ChannelHistory, Blacklist

from constants.db_constants import DEFAULT_PATTERNS
from constants.logger import LOG_DB


logger = logging.getLogger(__name__)


async def initialize_blacklist():
    async with get_db_session() as session:
        try:
            for pattern, reason in DEFAULT_PATTERNS.items():
                blacklist_db = await session.execute(
                    exists(Blacklist).where(
                        and_(Blacklist.pattern == pattern, Blacklist.reason == reason)
                    )
                )
                if not blacklist_db:
                    blacklist = Blacklist(pattern=pattern, reason=reason)
                    session.add(blacklist)
                    await session.commit()
                    await session.flush()
                    logger.info(LOG_DB["create_blacklist"])
                    return True
        except SQLAlchemyError as e:
            logging.error(LOG_DB["db_err"].format(error=e))
            return False


async def get_uncheked_posts_count():
    async with get_db_session() as session:
        try:
            result = await session.execute(
                select(Post).where(Post.is_processed == False)
            )
            posts = result.all()
            return len(posts)
        except SQLAlchemyError as e:
            logging.error(e)
            return False


async def export_data_to_csv():
    try:
        filename = f"export_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv"
        async with get_db_session() as session, open(
            filename, mode="w", newline="", encoding="utf-8-sig"
        ) as file:
            writer = csv.writer(file, delimiter=";", quoting=csv.QUOTE_MINIMAL)

            headers = [col for col in Post.__table__.cloumns]
            writer.writerow(headers)

            result = await session.execute(select(Post))
            posts = result.all()

            for post in posts:
                row = [getattr(post, col.name) for col in Post.__table__.columns]
                cleaned_row = [
                    (
                        str(item).replace(";", ",").strip()
                        if isinstance(item, str)
                        else item
                    )
                    for item in row
                ]
                writer.writerow(cleaned_row)
            logger.info(LOG_DB["export_csv"])
            return filename
    except Exception as e:
        logging.error(LOG_DB["db_err"].format(error=e))
        return False


async def save_post(
    check_date, post_date, channel_link, post_link, post_text, user_requested=0
):
    async with get_db_session() as session:
        try:
            post = Post(
                check_date=check_date,
                post_date=post_date,
                channel_link=channel_link,
                post_link=post_link,
                post_text=post_text,
                user_requested=user_requested,
            )
            session.add(post)
            await session.commit(post)
            await session.refresh(post)
            return True
        except SQLAlchemyError as e:
            logger.error(LOG_DB["db_err"].format(error=e))
            return False


async def add_channel(channel_link, source="parser"):
    channel_link = channel_link.split("/")[-1]
    async with get_db_session() as session:
        try:
            result = await session.execute(
                select(Channel).where(Channel.channel_link == channel_link)
            )
            channel = result.scalar_one_or_none()
            if not channel:
                new_channel = Channel(channel_link=channel_link, source=source)
                session.add(new_channel)
                await session.commit()
                await session.refresh(new_channel)
                return True
            channel.is_active = True
            await session.commit()
            await session.refresh(channel)
            return True
        except SQLAlchemyError as e:
            logger.error(LOG_DB["db_err"].format(error=e))
            return False


async def is_blacklisted(value: str, check_pattern: bool = False):
    async with get_db_session() as session:
        pass
