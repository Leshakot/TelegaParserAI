from aiogram import Bot, Dispatcher, Router, F
from aiogram.types import Message, ReplyKeyboardMarkup, KeyboardButton, ReplyKeyboardRemove
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from database.db import (
    get_unchecked_posts_count,
    export_data_to_csv,
    get_stats,
    get_unchecked_posts,
    mark_post_as_checked,
    add_channel,
    save_new_channels,
    get_cursor
)
import asyncio
from core.parser import parse_all_active_channels
from core.ai_filter import check_post
import re
from typing import List


# Создаем роутер
router = Router()

# Добавляем состояние для FSM
class ChannelStates(StatesGroup):
    waiting_for_channel = State()

# Состояния для FSM
class PostCheck(StatesGroup):
    checking = State()
    processing = State()


# Глобальные переменные для управления процессом проверки
current_check_task = None
stop_checking_flag = False


# Клавиатура с основными функциями
def get_main_keyboard():
    return ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text="✅ Добавить канал для проверки")],
            [KeyboardButton(text="👀 Парсинг постов")],
            [KeyboardButton(text="🔄 Проверить посты на м. схемы")],
            [KeyboardButton(text="📤 Выгрузить данные")],
            [KeyboardButton(text="🔍 Найти новые каналы")],
            [KeyboardButton(text="📜 Показать черный список")],
            [KeyboardButton(text="📊 Статистика")]
        ],
        resize_keyboard=True
    )


def get_stop_keyboard():
    return ReplyKeyboardMarkup(
        keyboard=[[KeyboardButton(text="🛑 Остановить проверку")]],
        resize_keyboard=True
    )


@router.message(Command("start"))
async def cmd_start(message: Message):
    await message.answer(
        "Выберите действие:",
        reply_markup=get_main_keyboard()
    )


@router.message(F.text == "✅ Добавить канал для проверки")
async def add_channel_command(message: Message, state: FSMContext):
    await message.answer(
        "Отправьте ссылку на канал (например: @channel_name или https://t.me/channel_name):",
        reply_markup=ReplyKeyboardRemove()
    )
    await state.set_state(ChannelStates.waiting_for_channel)


@router.message(ChannelStates.waiting_for_channel)
async def process_channel_link(message: Message, state: FSMContext):
    try:
        channel_link = message.text.strip()
        success = await add_channel(channel_link, source="user")

        if success:
            await message.answer(
                f"✅ Канал {channel_link} добавлен для мониторинга!",
                reply_markup=get_main_keyboard()
            )
        else:
            await message.answer(
                "❌ Не удалось добавить канал. Проверьте формат ссылки.",
                reply_markup=get_main_keyboard()
            )
    except Exception as e:
        await message.answer(
            f"❌ Ошибка: {str(e)}",
            reply_markup=get_main_keyboard()
        )
    finally:
        await state.clear()


@router.message(F.text == "👀 Парсинг постов")
async def parse_posts_handler(message: Message):
    # Вариант 1: Парсинг последнего добавленного канала
    await parse_all_active_channels(message)

    # Вариант 2: Парсинг всех каналов (раскомментировать если нужно)
    # asyncio.create_task(parse_all_channels())
    # await message.answer("🔍 Запущен парсинг всех активных каналов...")


@router.message(Command("parse"))
async def parse_with_limit(message: Message):
    try:
        limit = int(message.text.split()[1])
        await parse_all_active_channels(limit)
    except:
        await parse_all_active_channels()


@router.message(F.text == "🔄 Проверить посты на м. схемы")
async def check_new_posts(message: Message, state: FSMContext):
    count = await get_unchecked_posts_count()
    if count == 0:
        await message.answer("🤷 Нет новых постов для проверки")
        return

    await message.answer(
        f"🔍 Найдено {count} непроверенных постов. Начинаю проверку...",
        reply_markup=get_stop_keyboard()
    )

    global current_check_task, stop_checking_flag
    stop_checking_flag = False

    # Запускаем проверку в фоне
    current_check_task = asyncio.create_task(
        process_unchecked_posts(message, count)
    )

    await state.set_state(PostCheck.checking)


async def process_unchecked_posts(message: Message, total_count: int):
    checked_count = 0
    batch_size = 1  # Количество постов для проверки за один раз

    try:
        while not stop_checking_flag:
            posts = await get_unchecked_posts(limit=batch_size)
            if not posts:
                break

            for post_id, post_text in posts:
                if stop_checking_flag:
                    break

                # Здесь должна быть логика проверки через GigaChat
                # TODO
                is_recipe = await check_post(post_text)

                await mark_post_as_checked(post_id, is_recipe)
                checked_count += 1

                # if checked_count % 5 == 0:  # Отчет каждые 5 постов
                #     await message.answer(
                #         f"🔍 Проверено {checked_count}/{total_count} постов...",
                #         reply_markup=get_stop_keyboard()
                #     )
                await message.answer(
                    f"🔍 Проверено {checked_count}/{total_count} постов...",
                    reply_markup=get_stop_keyboard()
                )

            await asyncio.sleep(1)  # Задержка между пачками

        if stop_checking_flag:
            await message.answer(
                f"⏹ Проверка прервана. Проверено {checked_count}/{total_count} постов.",
                reply_markup=get_main_keyboard()
            )
        else:
            await message.answer(
                f"✅ Проверка завершена! Обработано {checked_count} постов.",
                reply_markup=get_main_keyboard()
            )

    except Exception as e:
        await message.answer(f"❌ Ошибка при проверке: {e}")
    finally:
        global current_check_task
        current_check_task = None


@router.message(F.text == "🛑 Остановить проверку")
async def stop_checking(message: Message, state: FSMContext):
    global stop_checking_flag
    stop_checking_flag = True
    await message.answer(
        "🛑 Останавливаю проверку...",
        reply_markup=ReplyKeyboardRemove()
    )
    await state.clear()


@router.message(F.text == "📤 Выгрузить данные")
async def export_data(message: Message):
    count = await get_unchecked_posts_count()
    if count > 0:
        file_path = await export_data_to_csv()
        with open(file_path, 'rb') as file:
            await message.answer_document(file, caption="📁 Ваши данные")
    else:
        await message.answer("📁 Нет данных для выгрузки")


@router.message(F.text == "🔍 Найти новые каналы")
async def handle_find_channels(message: Message):
    await message.answer("🕵️‍♂️ Начинаю поиск новых каналов...")

    try:
        # Ищем новые каналы
        new_channels = await search_new_channels()

        if not new_channels:
            await message.answer("🤷 Новых каналов не найдено")
            return

        # Сохраняем найденные каналы
        saved = await save_new_channels(new_channels)

        await message.answer(
            f"✅ Найдено {len(new_channels)} новых каналов\n"
            f"📥 Сохранено: {saved} каналов\n"
            f"Примеры: {', '.join(new_channels[:5])}..."
        )

    except Exception as e:
        await message.answer(f"❌ Ошибка при поиске каналов: {str(e)}")


@router.message(F.text == "📊 Статистика")
async def show_stats(message: Message):
    stats = await get_stats()
    text = (
        f"📊 Статистика:\n"
        f"• Всего постов: {stats['total_posts']}\n"
        f"• Рецептов: {stats['recipes']}\n"
        f"• Непроверенных: {stats['unchecked']}"
    )
    await message.answer(text)



async def search_new_channels() -> List[str]:
    """
    Ищет новые каналы в текстах постов из базы данных
    Возвращает список найденных уникальных каналов
    """
    # Регулярное выражение для поиска ссылок на каналы
    CHANNEL_REGEX = r'(?:https?://)?(?:t\.me/|@)([a-zA-Z0-9_]{5,32})'

    found_channels = set()  # Используем set для автоматического удаления дубликатов

    with get_cursor() as cur:
        # Получаем все непроверенные посты
        cur.execute("SELECT post_text FROM posts WHERE is_processed = 0")
        posts = cur.fetchall()

        for (post_text,) in posts:
            if not post_text:
                continue

            # Ищем все упоминания каналов в тексте поста
            matches = re.findall(CHANNEL_REGEX, post_text)
            for channel in matches:
                # Приводим к стандартному формату @username
                normalized = f"@{channel.lower()}"
                found_channels.add(normalized)

    # Исключаем уже известные каналы
    with get_cursor() as cur:
        cur.execute("SELECT channel_link FROM channels")
        existing_channels = {row[0].lower() for row in cur.fetchall()}

    # Возвращаем только новые каналы
    return [channel for channel in found_channels
            if channel not in existing_channels and
            not channel.startswith(('@durov', '@telegram'))]  # Исключаем служебные каналы


@router.message(Command("blacklist"))
async def manage_blacklist(message: Message, state: FSMContext):
    """Управление черным списком"""
    markup = ReplyKeyboardMarkup(keyboard=[
        [KeyboardButton(text="📜 Показать черный список")],
        [KeyboardButton(text="🚫 Добавить в черный список")],
        [KeyboardButton(text="✅ Удалить из черного списка")],
        [KeyboardButton(text="🔙 Назад")]
    ], resize_keyboard=True)

    await message.answer("Управление черным списком:", reply_markup=markup)


@router.message(F.text == "📜 Показать черный список")
async def show_blacklist(message: Message):
    """Показывает содержимое черного списка"""
    with get_cursor() as cur:
        items = cur.execute(
            "SELECT pattern, reason FROM blacklist ORDER BY added_date DESC LIMIT 50"
        ).fetchall()

    if not items:
        await message.answer("Черный список пуст")
        return

    text = "🚫 Черный список:\n" + "\n".join(
        f"• {item[0]} ({item[1] or 'без указания причины'})"
        for item in items
    )
    await message.answer(text[:4000])  # Ограничение длины сообщения

def setup_bot_handlers(dp: Dispatcher):
    dp.include_router(router)
