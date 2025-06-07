from datetime import datetime

from sqlalchemy import Integer, String, DateTime
from sqlalchemy.orm import DeclarativeBase, declared_attr, Mapped, mapped_column

from sqlalchemy.ext.asyncio import AsyncAttrs


class Base(DeclarativeBase, AsyncAttrs):
    __abstract__ = True

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)

    @declared_attr
    def __tablename__(self):
        return self.__name__.lower() + "s"


class Post(Base):
    check_date: Mapped[datetime] = mapped_column(
        DateTime,
        default=datetime.now,
        onupdate=datetime.now,
    )
    post_date: Mapped[datetime] = mapped_column(DateTime, nullable=True)
    channel_link: Mapped[str] = mapped_column(String, unique=True)
    post_link: Mapped[str] = mapped_column(String, unique=True)
    post_text: Mapped[str | None] = mapped_column(String)
    user_requested: Mapped[int | None] = mapped_column(Integer, default=0)
    is_recipe: Mapped[bool] = mapped_column(default=False)
    is_processed: Mapped[bool] = mapped_column(default=False)


class Channel(Base):
    channel_link: Mapped[str] = mapped_column(String, unique=True)
    added_date: Mapped[str] = mapped_column(
        DateTime, default=datetime.now, onupdate=datetime.now
    )
    is_active: Mapped[bool] = mapped_column(default=True)
    source: Mapped[str] = mapped_column(String)


class Blacklist(Base):
    pattern: Mapped[str] = mapped_column(String, unique=True)
    reason: Mapped[str] = mapped_column(String, nullable=True)
    added_date: Mapped[datetime] = mapped_column(
        DateTime, default=datetime.now, onupdate=datetime.now
    )


class ChannelHistory(Base):
    channel_link: Mapped[str] = mapped_column(String)
    status: Mapped[str | None] = mapped_column(String, nullable=True)
    last_checked: Mapped[datetime] = mapped_column(
        DateTime, default=datetime.now, onupdate=datetime.now
    )
    error_message: Mapped[str] = mapped_column(String, nullable=True)
