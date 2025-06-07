import pytest
from datetime import datetime
from sqlalchemy import select
from sqlalchemy.exc import SQLAlchemyError
from database.database import get_db_session
from database.models import Post
from database.db_commands import save_post


@pytest.mark.asyncio
async def test_save_new_post():
    channel_link = "test_link"
    post_link = "test_links_apost"
    check_date = datetime.now()
    post_date = datetime.now()
    post_text = "test"

    result = await save_post(check_date, post_date, channel_link, post_link, post_text)
    assert result == True

    async with get_db_session() as session:
        saved_post = await session.execute(
            select(Post).where(
                Post.channel_link == channel_link, Post.post_link == post_link
            )
        )
        assert saved_post.scalar_one_or_none() is not None
