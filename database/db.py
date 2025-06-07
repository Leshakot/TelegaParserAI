import sqlite3
import asyncio
from datetime import datetime
from contextlib import contextmanager
from typing import List
import os
import re

DATABASE = "data.db"


def init_db_sync():
    """Синхронная инициализация структуры БД"""
    with sqlite3.connect(DATABASE) as conn:
        cur = conn.cursor()
        # Таблица постов
        cur.execute(
            """
            CREATE TABLE IF NOT EXISTS posts (
                id INTEGER PRIMARY KEY,
                check_date DATETIME,
                post_date DATETIME,
                channel_link TEXT,
                post_link TEXT,
                post_text TEXT,
                user_requested INTEGER DEFAULT 0,
                is_recipe INTEGER DEFAULT 0,
                is_processed INTEGER DEFAULT 0,
                UNIQUE(channel_link, post_link)
            )
        """
        )
        # Таблица каналов
        cur.execute(
            """
            CREATE TABLE IF NOT EXISTS channels (
                id INTEGER PRIMARY KEY,
                channel_link TEXT UNIQUE,
                added_date DATETIME,
                is_active INTEGER DEFAULT 1,
                source TEXT
            )
        """
        )
        cur.execute(
            """
            CREATE TABLE IF NOT EXISTS blacklist (
                id INTEGER PRIMARY KEY,
                pattern TEXT UNIQUE,
                reason TEXT,
                added_date DATETIME DEFAULT CURRENT_TIMESTAMP
            )
        """
        )
        # Таблица истории каналов
        cur.execute(
            """
            CREATE TABLE IF NOT EXISTS channel_history (
                id INTEGER PRIMARY KEY,
                channel_link TEXT,
                status TEXT,
                last_checked DATETIME,
                error_message TEXT
            )
        """
        )
        # Таблица состояния парсинга
        cur.execute(
            """
            CREATE TABLE IF NOT EXISTS parsing_state (
                channel_link TEXT PRIMARY KEY,
                last_post_id INTEGER,
                last_parsed TIMESTAMP
            )
        """
        )
        conn.commit()


async def init_db():
    """Асинхронная инициализация БД"""
    await asyncio.to_thread(init_db_sync)


async def get_unchecked_posts_count():
    """Получает количество непроверенных постов"""
    with get_cursor() as cur:
        return cur.execute(
            "SELECT COUNT(*) FROM posts WHERE is_processed = 0"
        ).fetchone()[0]


async def initialize_blacklist():
    """Добавляет стандартные шаблоны в черный список при старте."""
    default_patterns = [
        ("admin", "Служебный псевдоним"),
        ("support", "Служебный псевдоним"),
        ("bot", "Служебный псевдоним"),
        ("telegram", "Официальный канал"),
        (
            "^[a-z]{1,3}$",
            "Слишком короткое имя канала",
        ),  # Используется как регулярное выражение
    ]

    with get_cursor() as cur:
        for pattern, reason in default_patterns:
            try:
                cur.execute(
                    "INSERT OR IGNORE INTO blacklist (pattern, reason) VALUES (?, ?)",
                    (pattern, reason),
                )
            except sqlite3.Error as e:
                print(f"Ошибка при добавлении шаблона '{pattern}': {e}")


async def ensure_db_initialized():
    """Гарантирует инициализацию БД"""
    if not os.path.exists(DATABASE):
        print("🛠 Создаем новую базу данных...")
        await init_db()
        print("🛠 База данных собрана")
    else:
        # Проверяем существование всех таблиц
        with get_cursor() as cur:
            tables = cur.execute(
                "SELECT name FROM sqlite_master WHERE type='table'"
            ).fetchall()
            existing_tables = {t[0] for t in tables}
            required_tables = {
                "posts",
                "channels",
                "parsing_state",
                "channel_history",
                "blacklist",
            }
            if not required_tables.issubset(existing_tables):
                print("🛠 Обновляем структуру базы данных...")
                await init_db()


async def export_data_to_csv():
    """
    Экспортирует все данные из таблицы posts в CSV-файл.
    Возвращает путь к созданному файлу.
    """
    import csv

    filename = f"export_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv"

    with get_cursor() as cur, open(
        filename, mode="w", newline="", encoding="utf-8-sig"
    ) as file:
        writer = csv.writer(file, delimiter=";", quoting=csv.QUOTE_MINIMAL)

        # Заголовки
        cur.execute("PRAGMA table_info(posts)")
        headers = [info[1] for info in cur.fetchall()]
        writer.writerow(headers)

        # Данные
        cur.execute("SELECT * FROM posts")
        for row in cur.fetchall():
            cleaned_row = []
            for item in row:
                if isinstance(item, str):
                    # Очищаем строковые значения
                    cleaned_item = item.replace(
                        ";", ","
                    ).strip()  # Избегаем разрыва данных
                    cleaned_row.append(cleaned_item)
                else:
                    cleaned_row.append(item)
            writer.writerow(cleaned_row)

    return filename


@contextmanager
def get_cursor():
    """Контекстный менеджер для работы с БД"""
    conn = sqlite3.connect(DATABASE)
    conn.execute("PRAGMA journal_mode=WAL")
    try:
        yield conn.cursor()
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


async def ensure_db_exists():
    """Проверяет и создает БД при необходимости"""
    import os

    if not os.path.exists(DATABASE):
        print("🛠 Создаем новую БД...")
        await init_db()


async def save_post(
    check_date, post_date, channel_link, post_link, post_text, user_requested=0
):
    """Сохранение поста в базу данных с проверкой на дубликаты"""
    with get_cursor() as cur:
        try:
            cur.execute(
                """
                INSERT INTO posts 
                (check_date, post_date, channel_link, post_link, post_text, user_requested)
                VALUES (?, ?, ?, ?, ?, ?)
                ON CONFLICT(channel_link, post_link) DO NOTHING
            """,
                (
                    check_date,
                    post_date,
                    channel_link,
                    post_link,
                    post_text,
                    user_requested,
                ),
            )
            return True
        except sqlite3.Error as e:
            print(f"Ошибка при сохранении поста: {e}")
            return False


async def add_channel(channel_link, source="parser"):
    """Добавление нового канала в базу для мониторинга"""
    channel_link = channel_link.split("/")[-1]
    with get_cursor() as cur:
        try:
            cur.execute(
                """
                INSERT INTO channels (channel_link, added_date, source)
                VALUES (?, ?, ?)
                ON CONFLICT(channel_link) DO UPDATE SET is_active=1
            """,
                (channel_link, datetime.now(), source),
            )
            return True
        except sqlite3.Error as e:
            print(f"Ошибка при добавлении канала: {e}")
            return False


async def is_blacklisted(value: str, check_pattern: bool = False) -> bool:
    """
    Проверяет, находится ли значение в черном списке.

    :param value: Значение для проверки (канал или имя пользователя)
    :param check_pattern: Если True, ищет совпадение по шаблонам
    :return: True, если найдено в чёрном списке
    """
    with get_cursor() as cur:
        if check_pattern:
            # Ищем совпадение регулярных выражений
            cur.execute("SELECT pattern FROM blacklist")
            patterns = [row[0] for row in cur.fetchall()]
            for pattern in patterns:
                try:
                    if re.search(pattern, value):
                        return True
                except re.error:
                    continue
            return False
        else:
            # Простая проверка на наличие точного совпадения
            cur.execute("SELECT 1 FROM blacklist WHERE pattern = ?", (value,))
            return cur.fetchone() is not None


async def add_to_blacklist(pattern: str, reason: str = "") -> bool:
    """Добавляет шаблон в черный список"""
    with get_cursor() as cur:
        try:
            cur.execute(
                "INSERT OR IGNORE INTO blacklist (pattern, reason) VALUES (?, ?)",
                (pattern, reason),
            )
            return cur.rowcount > 0
        except sqlite3.Error as e:
            print(f"Ошибка добавления в черный список: {e}")
            return False


async def save_new_channels(channels: List[str], source: str = "auto_find") -> int:
    saved_count = 0
    with get_cursor() as cur:
        for channel in channels:
            try:
                link = (
                    f"https://t.me/ {channel[1:]}"  # @username → https://t.me/username
                )
                cur.execute(
                    "INSERT OR IGNORE INTO channels (channel_link, added_date, source) VALUES (?, ?, ?)",
                    (link, datetime.now(), source),
                )
                if cur.rowcount > 0:
                    saved_count += 1
            except sqlite3.Error as e:
                print(f"Ошибка сохранения канала {channel}: {e}")
    return saved_count


async def mark_post_as_checked(post_id, is_recipe):
    with get_cursor() as cur:
        try:
            cur.execute(
                """
                UPDATE posts 
                SET is_processed = 1, 
                    is_recipe = ? 
                WHERE id = ?
            """,
                (1 if is_recipe else 0, post_id),
            )
            return cur.rowcount > 0
        except sqlite3.Error as e:
            print(f"Ошибка при обновлении поста: {e}")
            return False


async def get_unchecked_posts(limit=None):
    with get_cursor() as cur:
        query = "SELECT id, post_text FROM posts WHERE is_processed = 0"
        if limit:
            query += f" LIMIT {limit}"
        return cur.execute(query).fetchall()


async def get_active_channels():
    """Получение списка активных каналов для мониторинга"""
    with get_cursor() as cur:
        return [
            row[0]
            for row in cur.execute(
                "SELECT channel_link FROM channels WHERE is_active = 1"
            ).fetchall()
        ]


async def deactivate_channel(channel_link: str, error_message: str = ""):
    """Деактивирует канал и сохраняет ошибку"""
    with get_cursor() as cur:
        try:
            # Обновляем статус в channels
            cur.execute(
                "UPDATE channels SET is_active = 0 WHERE channel_link = ?",
                (channel_link,),
            )
            # Добавляем запись в историю
            cur.execute(
                """INSERT INTO channel_history 
                (channel_link, status, error_message) 
                VALUES (?, 'inactive', ?)""",
                (channel_link, error_message[:500]),  # Ограничиваем длину сообщения
            )
        except sqlite3.Error as e:
            print(f"Ошибка деактивации канала: {e}")


async def get_stats():
    await ensure_db_initialized()
    with get_cursor() as cur:
        return {
            "total_posts": cur.execute("SELECT COUNT(*) FROM posts").fetchone()[0],
            "recipes": cur.execute(
                "SELECT COUNT(*) FROM posts WHERE is_recipe = 1"
            ).fetchone()[0],
            "unchecked": cur.execute(
                "SELECT COUNT(*) FROM posts WHERE is_processed = 0"
            ).fetchone()[0],
        }
