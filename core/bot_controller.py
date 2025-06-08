import re
import logging
import asyncio
from typing import List

from aiogram import Dispatcher, Router, F
from aiogram.types import (
    Message,
    ReplyKeyboardMarkup,
    KeyboardButton,
    ReplyKeyboardRemove,
    CallbackQuery,
    FSInputFile,
)
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup

from database.db_commands import (
    get_unchecked_posts_count,
    export_data_to_csv,
    get_stats,
    get_unchecked_posts,
    mark_post_as_checked,
    add_channel,
    save_new_channels,
    get_posts_for_search,
    get_channel_links,
    get_blacklist_pat_reason,
)

from core.clients import telegram_client  # <-- ваш клиент Telethon
from core.parser import parse_all_active_channels, parse_channel
from core.ai_filter import check_post
from core.states import ChannelStates, PostCheck

from keyboards.keyboards import (
    get_main_keyboard,
    get_stop_keyboard,
    parse_channel_keyboard,
)


# Настройка логирования
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


router = Router()


# Глобальные переменные для управления процессом проверки
CURRENT_CHECK_TASK = None
STOP_CHECKING_FLAG = False


@router.message(Command("start"))
async def cmd_start(message: Message):
    await message.answer("Выберите действие:", reply_markup=get_main_keyboard())


@router.message(F.text == "✅ Добавить канал для проверки")
async def add_channel_command(message: Message, state: FSMContext):
    await message.answer(
        "Отправьте ссылку на канал (например: @channel_name или https://t.me/channel_name ):",
        reply_markup=ReplyKeyboardRemove(),
    )
    await state.set_state(ChannelStates.waiting_for_channel)


@router.message(ChannelStates.waiting_for_channel)
async def process_channel_link(message: Message, state: FSMContext):
    try:
        channel_link = message.text.strip()
        await state.update_data(channel_link=channel_link)
        success = await add_channel(channel_link, source="user")
        if success:
            await state.set_state(ChannelStates.choosing_action)
            await message.answer(
                f"✅ Канал {channel_link} добавлен для мониторинга!",
                reply_markup=get_main_keyboard(),
            )
            await message.answer(
                "Выберите действие:", reply_markup=parse_channel_keyboard
            )
        else:
            await message.answer(
                "❌ Не удалось добавить канал. Проверьте формат ссылки.",
                reply_markup=get_main_keyboard(),
            )
            await state.clear()
    except Exception as e:
        await message.answer(f"❌ Ошибка: {str(e)}", reply_markup=get_main_keyboard())
        await state.clear()


@router.callback_query(ChannelStates.choosing_action)
async def process_channel_action(callback_query: CallbackQuery, state: FSMContext):
    field = callback_query.data.strip()
    print("field")
    match field:
        case "inplace_parse_channel":
            data = await state.get_data()
            channel_link = data.get("channel_link")
            print(channel_link)
            total_saved = await parse_channel(telegram_client, channel_link, limit=10)
            await callback_query.message.answer(
                f"✅ Парсинг завершён. Сохранено постов: {total_saved}"
            )
            await callback_query.answer()
        case "back_to_menu":
            await callback_query.message.answer(
                f"Выберите действие:", reply_markup=get_main_keyboard()
            )
        case _:
            await callback_query.message.answer(
                "Нет такого действия.", reply_markup=get_main_keyboard()
            )
    await state.clear()


@router.message(F.text == "👀 Парсинг постов")
async def parse_posts_handler(message: Message):
    await message.answer("🔍 Подключаюсь к Telegram для парсинга...")

    # if not telegram_client.is_connected():
    #     try:
    #         await telegram_client.connect()
    #         if not await telegram_client.is_user_authorized():
    #             await message.answer("❌ Telethon клиент не авторизован.")
    #             logger.error("❌ Telethon клиент не авторизован.")
    #             return
    #     except Exception as e:
    #         logger.critical(f"🔴 Ошибка подключения Telethon клиента: {e}")
    #         await message.answer("⚠️ Не удалось подключиться к Telegram API.")
    #         return

    try:
        print("Begin save posts")
        total_saved = await parse_all_active_channels(
            client=telegram_client, limit_per_channel=10
        )
        if total_saved > 0:
            await message.answer(
                f"✅ Парсинг завершён. Сохранено постов: {total_saved}"
            )
        else:
            await message.answer("ℹ️ Новых постов для сохранения не найдено.")
    except Exception as e:
        logger.exception("Ошибка при выполнении парсинга")
        await message.answer("❗ Произошла ошибка при парсинге каналов.")


@router.message(Command("parse"))
async def parse_with_limit(message: Message):
    try:
        limit = int(message.text.split()[1])
        await parse_all_active_channels(limit)
    except:
        await parse_all_active_channels()


@router.message(F.text == "🔄 Проверить посты на м. схемы")
async def check_new_posts(message: Message, state: FSMContext):
    count = await get_unchecked_posts_count()  # while db sync
    if count == 0:
        await message.answer("🤷 Нет новых постов для проверки")
        return
    await message.answer(
        f"🔍 Найдено {count} непроверенных постов. Начинаю проверку...",
        reply_markup=get_stop_keyboard(),
    )
    global CURRENT_CHECK_TASK, STOP_CHECKING_FLAG
    STOP_CHECKING_FLAG = False
    # Запускаем проверку в фоне
    CURRENT_CHECK_TASK = asyncio.create_task(process_unchecked_posts(message, count))
    await state.set_state(PostCheck.checking)


async def process_unchecked_posts(message: Message, total_count: int):
    checked_count = 0
    batch_size = 1
    try:
        while not STOP_CHECKING_FLAG:
            posts = await get_unchecked_posts(limit=batch_size)  # while db is sync
            if not posts:
                break
            for post_id, post_text in posts:
                if STOP_CHECKING_FLAG:
                    break
                is_recipe = await check_post(post_text)
                await mark_post_as_checked(post_id, is_recipe)  # while db is sync
                checked_count += 1
                await message.answer(
                    f"🔍 Проверено {checked_count}/{total_count} постов...",
                    reply_markup=get_stop_keyboard(),
                )
            await asyncio.sleep(1)
        if STOP_CHECKING_FLAG:
            await message.answer(
                f"⏹ Проверка прервана. Проверено {checked_count}/{total_count} постов.",
                reply_markup=get_main_keyboard(),
            )
        else:
            await message.answer(
                f"✅ Проверка завершена! Обработано {checked_count} постов.",
                reply_markup=get_main_keyboard(),
            )
    except Exception as e:
        await message.answer(f"❌ Ошибка при проверке: {e}")
    finally:
        global CURRENT_CHECK_TASK
        CURRENT_CHECK_TASK = None


@router.message(F.text == "🛑 Остановить проверку")
async def stop_checking(message: Message, state: FSMContext):
    global STOP_CHECKING_FLAG
    STOP_CHECKING_FLAG = True
    await message.answer(
        "🛑 Останавливаю проверку...", reply_markup=ReplyKeyboardRemove()
    )
    await state.clear()


@router.message(F.text == "📤 Выгрузить данные")
async def export_data(message: Message):
    count = await get_unchecked_posts_count()  # while db sync
    print(count)
    if count > 0:
        file_path = await export_data_to_csv()
        await message.answer_document(FSInputFile(file_path), caption="📁 Ваши данные")
        # with open(file_path, "rb") as file:
        #     await message.answer_document(file, caption="📁 Ваши данные")
    else:
        await message.answer("📁 Нет данных для выгрузки")


@router.message(F.text == "🔍 Найти новые каналы")
async def handle_find_channels(message: Message):
    await message.answer("🕵️‍♂️ Начинаю поиск новых каналов...")
    try:
        new_channels = await search_new_channels()
        if not new_channels:
            await message.answer("🤷 Новых каналов не найдено")
            return
        saved = await save_new_channels(new_channels)  # while db is sync
        await message.answer(
            f"✅ Найдено {len(new_channels)} новых каналов\n"
            f"📥 Сохранено: {saved} каналов\n"
            f"Примеры: {', '.join(new_channels[:5])}..."
        )
    except Exception as e:
        await message.answer(f"❌ Ошибка при поиске каналов: {str(e)}")


@router.message(F.text == "📊 Статистика")
async def show_stats(message: Message):
    stats = await get_stats()  # while db is sync
    text = (
        f"📊 Статистика:\n"
        f"• Всего постов: {stats['total_posts']}\n"
        f"• Рецептов: {stats['recipes']}\n"
        f"• Непроверенных: {stats['unchecked']}"
    )
    await message.answer(text)


async def search_new_channels() -> List[str]:
    CHANNEL_REGEX = r"(?:https?://)?(?:t\.me/|@)([a-zA-Z0-9_]{5,32})"
    found_channels = set()

    posts = await get_posts_for_search()
    for (post_text,) in posts:
        if not post_text:
            continue
        matches = re.findall(CHANNEL_REGEX, post_text)
        for channel in matches:
            normalized = f"@{channel.lower()}"
            found_channels.add(normalized)
    existing_channels = await get_channel_links()
    return [
        channel
        for channel in found_channels
        if channel not in existing_channels
        and not channel.startswith(("@durov", "@telegram"))
    ]


@router.message(Command("blacklist"))
async def manage_blacklist(message: Message, state: FSMContext):
    markup = ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text="📜 Показать черный список")],
            [KeyboardButton(text="🚫 Добавить в черный список")],
            [KeyboardButton(text="✅ Удалить из черного списка")],
            [KeyboardButton(text="🔙 Назад")],
        ],
        resize_keyboard=True,
    )
    await message.answer("Управление черным списком:", reply_markup=markup)


@router.message(F.text == "📜 Показать черный список")
async def show_blacklist(message: Message):
    items = await get_blacklist_pat_reason()
    if not items:
        await message.answer("Черный список пуст")
        return
    text = "🚫 Черный список:\n" + "\n".join(
        f"• {item[0]} ({item[1] or 'без указания причины'})" for item in items
    )
    await message.answer(text[:4000])


def setup_bot_handlers(dp: Dispatcher):
    dp.include_router(router)
