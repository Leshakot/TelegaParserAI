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
    InlineKeyboardMarkup,
    InlineKeyboardButton
)
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext

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

from core.parser import parse_all_active_channels, parse_channel
from core.ai_filter import check_post
from core.states import ChannelStates, PostCheck

from utils.logger import setup_logger


# Глобальные переменные для управления процессом проверки
CURRENT_CHECK_TASK = None
STOP_CHECKING_FLAG = False

logger = setup_logger()

router = Router()

# Define keyboards properly
def get_main_keyboard():
    return ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text="✅ Добавить канал для проверки"), KeyboardButton(text="👀 Парсинг постов")],
            [KeyboardButton(text="🔄 Проверить посты на м. схемы"), KeyboardButton(text="📤 Выгрузить данные")],
            [KeyboardButton(text="🔍 Найти новые каналы"), KeyboardButton(text="📊 Статистика")],
            [KeyboardButton(text="/blacklist")]
        ],
        resize_keyboard=True
    )

def get_stop_keyboard():
    return ReplyKeyboardMarkup(
        keyboard=[[KeyboardButton(text="🛑 Остановить проверку")]],
        resize_keyboard=True
    )

# Define the parse_channel_keyboard as a variable
parse_channel_keyboard = InlineKeyboardMarkup(
    inline_keyboard=[
        [InlineKeyboardButton(text="Парсить канал сейчас", callback_data="inplace_parse_channel")],
        [InlineKeyboardButton(text="Назад в меню", callback_data="back_to_menu")]
    ]
)


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
            total_saved = await parse_channel(channel_link, limit=10)
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
    """
    Handler for parsing posts with different modes:
    - Last N posts
    - Last N months
    - All posts
    """
    # Создаем клавиатуру для выбора режима парсинга
    keyboard = ReplyKeyboardMarkup(
        keyboard=[
            [
                KeyboardButton(text="📥 Последние 50 постов"),
                KeyboardButton(text="📅 За период")
            ],
            [
                KeyboardButton(text="📚 Все посты"),
                KeyboardButton(text="❌ Отмена")
            ]
        ],
        resize_keyboard=True
    )
    
    await message.answer("Выберите режим парсинга:", reply_markup=keyboard)


@router.message(F.text == "📥 Последние 50 постов")
async def parse_latest_posts(message: Message):
    await message.answer("🔍 Подключаюсь к Telegram для парсинга последних постов...")
    try:
        total_saved = await parse_all_active_channels(limit_per_channel=50)
        if total_saved > 0:
            await message.answer(f"✅ Парсинг завершён. Сохранено постов: {total_saved}", 
                                reply_markup=get_main_keyboard())
        else:
            await message.answer("ℹ️ Новых постов для сохранения не найдено.", 
                                reply_markup=get_main_keyboard())
    except Exception as e:
        logger.exception("Ошибка при выполнении парсинга")
        await message.answer("❗ Произошла ошибка при парсинге каналов.", 
                            reply_markup=get_main_keyboard())


@router.message(F.text == "📅 За период")
async def parse_by_period(message: Message):
    keyboard = ReplyKeyboardMarkup(
        keyboard=[
            [
                KeyboardButton(text="1 месяц"),
                KeyboardButton(text="3 месяца"),
                KeyboardButton(text="6 месяцев")
            ],
            [KeyboardButton(text="❌ Отмена")]
        ],
        resize_keyboard=True
    )
    await message.answer("Выберите период парсинга:", reply_markup=keyboard)


@router.message(F.text.in_({"1 месяц", "3 месяца", "6 месяцев"}))
async def parse_months(message: Message):
    months_map = {"1 месяц": 1, "3 месяца": 3, "6 месяцев": 6}
    months = months_map[message.text]
    
    await message.answer(f"🔍 Начинаю парсинг за последние {months} месяца(ев)...")
    try:
        total_saved = await parse_all_active_channels(months=months)
        if total_saved > 0:
            await message.answer(f"✅ Парсинг завершён. Сохранено постов: {total_saved}", 
                                reply_markup=get_main_keyboard())
        else:
            await message.answer("ℹ️ Новых постов для сохранения не найдено.", 
                                reply_markup=get_main_keyboard())
    except Exception as e:
        logger.exception("Ошибка при выполнении парсинга")
        await message.answer("❗ Произошла ошибка при парсинге каналов.", 
                            reply_markup=get_main_keyboard())


@router.message(F.text == "📚 Все посты")
async def parse_all_posts(message: Message):
    await message.answer("⚠️ Внимание! Парсинг всех постов может занять длительное время.")
    confirmation_keyboard = ReplyKeyboardMarkup(
        keyboard=[
            [
                KeyboardButton(text="✅ Подтвердить"),
                KeyboardButton(text="❌ Отмена")
            ]
        ],
        resize_keyboard=True
    )
    await message.answer("Подтвердите начало полного парсинга:", reply_markup=confirmation_keyboard)


@router.message(F.text == "✅ Подтвердить")
async def confirm_full_parse(message: Message):
    await message.answer("🔍 Начинаю полный парсинг всех каналов...")
    try:
        total_saved = await parse_all_active_channels(all_time=True)
        if total_saved > 0:
            await message.answer(f"✅ Полный парсинг завершён. Сохранено постов: {total_saved}", 
                                reply_markup=get_main_keyboard())
        else:
            await message.answer("ℹ️ Новых постов для сохранения не найдено.", 
                                reply_markup=get_main_keyboard())
    except Exception as e:
        logger.exception("Ошибка при выполнении парсинга")
        await message.answer("❗ Произошла ошибка при парсинге каналов.", 
                            reply_markup=get_main_keyboard())


@router.message(F.text == "❌ Отмена")
async def cancel_parsing(message: Message):
    await message.answer("🚫 Парсинг отменен", reply_markup=get_main_keyboard())


@router.message(F.text == "🔄 Проверить посты на м. схемы")
async def check_new_posts(message: Message, state: FSMContext):
    count = await get_unchecked_posts_count()
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
            posts = await get_unchecked_posts(limit=batch_size)
            if not posts:
                break
            for post_id, post_text in posts:
                if STOP_CHECKING_FLAG:
                    break
                is_recipe = await check_post(post_text)
                await mark_post_as_checked(post_id, is_recipe)
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
    count = await get_unchecked_posts_count()
    print(count)
    if count > 0:
        file_path = await export_data_to_csv()
        await message.answer_document(FSInputFile(file_path), caption="📁 Ваши данные")
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


@router.message(F.text == "🔙 Назад")
async def back_to_main_menu(message: Message):
    await message.answer("Возвращаюсь в главное меню", reply_markup=get_main_keyboard())


def setup_bot_handlers(dp: Dispatcher):
    dp.include_router(router)
