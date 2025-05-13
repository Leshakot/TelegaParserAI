import sqlite3
import csv
import asyncio
from datetime import datetime
from contextlib import contextmanager
from typing import List
import os

DATABASE = "data.db"


def init_db_sync():
    """Синхронная инициализация структуры БД"""
    with sqlite3.connect(DATABASE) as conn:
        cur = conn.cursor()

        # Таблица постов
        cur.execute("""
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
        """)

        # Таблица каналов
        cur.execute("""
            CREATE TABLE IF NOT EXISTS channels (
                id INTEGER PRIMARY KEY,
                channel_link TEXT UNIQUE,
                added_date DATETIME,
                is_active INTEGER DEFAULT 1,
                source TEXT
            )
        """)

        cur.execute("""
            CREATE TABLE IF NOT EXISTS blacklist (
                id INTEGER PRIMARY KEY,
                pattern TEXT UNIQUE,
                reason TEXT,
                added_date DATETIME DEFAULT CURRENT_TIMESTAMP
            )
        """)

        # Таблица истории каналов
        cur.execute("""
            CREATE TABLE IF NOT EXISTS channel_history (
                id INTEGER PRIMARY KEY,
                channel_link TEXT,
                status TEXT,
                last_checked DATETIME,
                error_message TEXT
            )
        """)

        # Таблица состояния парсинга
        cur.execute("""
            CREATE TABLE IF NOT EXISTS parsing_state (
                channel_link TEXT PRIMARY KEY,
                last_post_id INTEGER,
                last_parsed TIMESTAMP
            )
        """)

        conn.commit()


async def init_db():
    """Асинхронная инициализация БД"""
    await asyncio.to_thread(init_db_sync)


async def ensure_db_initialized():
    """Гарантирует инициализацию БД"""
    if not os.path.exists(DATABASE):
        print("🛠 Создаем новую базу данных...")
        await init_db()
        print("🛠 База данных собрана")
    else:
        # Проверяем существование всех таблиц
        with get_cursor() as cur:
            tables = cur.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()
            existing_tables = {t[0] for t in tables}
            required_tables = {
                'posts',
                'channels',
                'parsing_state',
                'channel_history',
                'blacklist',
                #'channel'
            }

            if not required_tables.issubset(existing_tables):
                print("🛠 Обновляем структуру базы данных...")
                await init_db()


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

async def save_post(check_date, post_date, channel_link, post_link, post_text, user_requested=0):
    """Сохранение поста в базу данных с проверкой на дубликаты"""
    with get_cursor() as cur:
        try:
            cur.execute('''
                INSERT INTO posts 
                (check_date, post_date, channel_link, post_link, post_text, user_requested)
                VALUES (?, ?, ?, ?, ?, ?)
                ON CONFLICT(channel_link, post_link) DO NOTHING
            ''', (check_date, post_date, channel_link, post_link, post_text, user_requested))
            return True
        except sqlite3.Error as e:
            print(f"Ошибка при сохранении поста: {e}")
            return False


async def add_channel(channel_link, source="parser"):
    """Добавление нового канала в базу для мониторинга"""
    channel_link = channel_link.split('/')[-1]
    with get_cursor() as cur:
        try:
            cur.execute('''
                INSERT INTO channels (channel_link, added_date, source)
                VALUES (?, ?, ?)
                ON CONFLICT(channel_link) DO UPDATE SET is_active=1
            ''', (channel_link, datetime.now(), source))
            return True
        except sqlite3.Error as e:
            print(f"Ошибка при добавлении канала: {e}")
            return False


async def get_channels_to_monitor(active_only=True):
    """Получение списка каналов для мониторинга"""
    with get_cursor() as cur:
        query = "SELECT channel_link FROM channels"
        if active_only:
            query += " WHERE is_active = 1"
        return [row[0] for row in cur.execute(query).fetchall()]


async def update_channel_status(channel_link, is_active):
    """Обновление статуса канала (активен/неактивен)"""
    with get_cursor() as cur:
        cur.execute('''
            UPDATE channels SET is_active = ? WHERE channel_link = ?
        ''', (is_active, channel_link))
        return cur.rowcount > 0


async def save_new_channel(channel_data, source="parser"):
    """
    Сохранение нового канала в базу данных
    :param channel_data: Может быть:
        - str: ссылка на канал (например, "https://t.me/channel" или "@channel")
        - list/iterable: список ссылок на каналы
        - str: текст поста, из которого нужно извлечь каналы
    :param source: источник канала ("parser", "user", "auto_find" и т.д.)
    :return: кортеж (total_processed, saved_count, duplicates_count)
    """

    def normalize_channel_link(link):
        """Приводит ссылку к стандартному формату https://t.me/channel"""
        link = link.strip()
        if link.startswith("@"):
            return f"https://t.me/{link[1:]}"
        if not link.startswith(("http://", "https://")):
            return f"https://t.me/{link}"
        return link.split('?')[0]  # Убираем параметры запроса

    processed = 0
    saved = 0
    duplicates = 0

    with get_cursor() as cur:
        # Если передана строка с текстом поста (ищем ссылки)
        if isinstance(channel_data, str) and ("t.me/" in channel_data or "@" in channel_data):
            import re
            channel_links = re.findall(r'(?:@|t\.me/)([a-zA-Z0-9_]{5,32})', channel_data)
            channel_data = [f"https://t.me/{link}" for link in set(channel_links)]

        # Если передана одиночная ссылка
        elif isinstance(channel_data, str):
            channel_data = [channel_data]

        for raw_link in channel_data:
            try:
                link = normalize_channel_link(raw_link)
                processed += 1

                cur.execute('''
                    INSERT INTO channels (channel_link, added_date, source)
                    VALUES (?, ?, ?)
                    ON CONFLICT(channel_link) DO UPDATE SET 
                        is_active=EXCLUDED.is_active,
                        source=EXCLUDED.source
                ''', (link, datetime.now(), source))

                if cur.rowcount > 0:
                    saved += 1
                else:
                    duplicates += 1

            except (ValueError, sqlite3.Error) as e:
                print(f"Ошибка при обработке канала {raw_link}: {e}")
                continue

    return (processed, saved, duplicates)


async def get_unchecked_posts_count():
    with get_cursor() as cur:
        return cur.execute("SELECT COUNT(*) FROM posts WHERE is_processed = 0").fetchone()[0]


async def get_unchecked_posts(limit=None):
    """Получение списка непроверенных постов из базы данных"""
    with get_cursor() as cur:
        query = "SELECT id, post_text FROM posts WHERE is_processed = 0"
        if limit:
            query += f" LIMIT {limit}"
        return cur.execute(query).fetchall()


async def mark_post_as_checked(post_id, is_recipe):
    """Пометка поста как проверенного с указанием, является ли он рецептом"""
    with get_cursor() as cur:
        try:
            cur.execute('''
                UPDATE posts 
                SET is_processed = 1, 
                    is_recipe = ? 
                WHERE id = ?
            ''', (1 if is_recipe else 0, post_id))
            return cur.rowcount > 0
        except sqlite3.Error as e:
            print(f"Ошибка при обновлении поста: {e}")
            return False


async def export_data_to_csv():
    filename = f"export_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv"
    with get_cursor() as cur, open(filename, 'w', newline='', encoding='utf-8-sig') as file:
        # Создаем writer с указанием разделителя ";"
        writer = csv.writer(file, delimiter=';', quoting=csv.QUOTE_MINIMAL)
        writer.writerow(['ID', 'Channel', 'Post ID', 'Text', 'Date', 'Is Recipe'])

        for row in cur.execute("SELECT * FROM posts"):
            # Обрабатываем каждое поле для корректного сохранения
            cleaned_row = []
            for item in row:
                if isinstance(item, str):
                    # Удаляем существующие точки с запятой в тексте, чтобы не нарушать формат
                    cleaned_item = item.replace(';', ' ').strip()
                    cleaned_row.append(cleaned_item)
                else:
                    cleaned_row.append(item)
            writer.writerow(cleaned_row)

    return filename


async def get_stats():
    await ensure_db_initialized()  # Добавьте эту строку
    with get_cursor() as cur:
        return {
            'total_posts': cur.execute("SELECT COUNT(*) FROM posts").fetchone()[0],
            'recipes': cur.execute("SELECT COUNT(*) FROM posts WHERE is_recipe = 1").fetchone()[0],
            'unchecked': cur.execute("SELECT COUNT(*) FROM posts WHERE is_processed = 0").fetchone()[0]
        }

async def get_active_channels():
    """Получение списка активных каналов для мониторинга"""
    with get_cursor() as cur:
        return [row[0] for row in cur.execute(
            "SELECT channel_link FROM channels WHERE is_active = 1"
        ).fetchall()]

async def channel_exists(channel_link: str) -> bool:
    """Проверка существования канала в базе"""
    with get_cursor() as cur:
        return cur.execute(
            "SELECT 1 FROM channels WHERE channel_link = ?",
            (channel_link,)
        ).fetchone() is not None

async def is_post_parsed(channel_link: str, post_id: int) -> bool:
    with get_cursor() as cur:
        return cur.execute(
            "SELECT 1 FROM posts WHERE channel_link = ? AND post_link LIKE ?",
            (channel_link, f"%/{post_id}")
        ).fetchone() is not None


async def get_last_post_id(channel_link: str) -> int:
    """
    Получает ID последнего обработанного поста для канала.
    Возвращает None если канал новый или нет постов.
    """
    try:
        with get_cursor() as cur:
            # Проверяем существование столбца post_id
            cur.execute("PRAGMA table_info(posts)")
            columns = [row[1] for row in cur.fetchall()]

            if 'post_id' not in columns:
                # Если столбца нет, используем id как post_id
                result = cur.execute(
                    "SELECT id FROM posts "
                    "WHERE channel_link = ? "
                    "ORDER BY id DESC LIMIT 1",
                    (channel_link,)
                ).fetchone()
            else:
                # Стандартный запрос если столбец существует
                result = cur.execute(
                    "SELECT post_id FROM posts "
                    "WHERE channel_link = ? "
                    "ORDER BY post_id DESC LIMIT 1",
                    (channel_link,)
                ).fetchone()

            return result[0] if result else None

    except sqlite3.Error as e:
        print(f"Ошибка при получении последнего post_id: {e}")
        return None

async def save_new_channels(channels: List[str], source: str = "auto_find") -> int:
    """
    Сохраняет новые каналы в базу данных
    :param channels: Список каналов (формат @username)
    :param source: Источник обнаружения
    :return: Количество сохраненных каналов
    """
    saved_count = 0
    with get_cursor() as cur:
        for channel in channels:
            try:
                # Преобразуем @username в https://t.me/username
                link = f"https://t.me/{channel[1:]}"
                cur.execute(
                    "INSERT OR IGNORE INTO channels (channel_link, added_date, source) "
                    "VALUES (?, datetime('now'), ?)",
                    (link, source)
                )
                if cur.rowcount > 0:
                    saved_count += 1
            except sqlite3.Error as e:
                print(f"Ошибка сохранения канала {channel}: {e}")
    return saved_count


async def add_to_blacklist(pattern: str, reason: str = "") -> bool:
    """Добавляет шаблон в черный список"""
    with get_cursor() as cur:
        try:
            cur.execute(
                "INSERT OR IGNORE INTO blacklist (pattern, reason) VALUES (?, ?)",
                (pattern.lower(), reason)
            )
            return cur.rowcount > 0
        except sqlite3.Error as e:
            print(f"Ошибка добавления в черный список: {e}")
            return False


async def is_blacklisted(channel_link: str) -> bool:
    """Проверяет, находится ли канал в черном списке"""
    with get_cursor() as cur:
        try:
            # Проверяем точные совпадения и шаблоны
            result = cur.execute(
                "SELECT 1 FROM blacklist WHERE ? LIKE '%' || pattern || '%'",
                (channel_link.lower(),)
            ).fetchone()
            return result is not None
        except sqlite3.Error as e:
            print(f"Ошибка проверки черного списка: {e}")
            return False


async def deactivate_channel(channel_link: str, error_message: str = ""):
    """Деактивирует канал и сохраняет ошибку"""
    with get_cursor() as cur:
        try:
            # Обновляем статус в channels
            cur.execute(
                "UPDATE channels SET is_active = 0 WHERE channel_link = ?",
                (channel_link,)
            )

            # Добавляем запись в историю
            cur.execute(
                """INSERT INTO channel_history 
                (channel_link, status, error_message) 
                VALUES (?, 'inactive', ?)""",
                (channel_link, error_message[:500])  # Ограничиваем длину сообщения
            )

            # Автоматически добавляем в черный список при определенных ошибках
            if "username is unacceptable" in error_message:
                await add_to_blacklist(channel_link.split('/')[-1], "Недопустимое имя пользователя")
        except sqlite3.Error as e:
            print(f"Ошибка деактивации канала: {e}")
