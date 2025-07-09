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
    export_data_to_excel,
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

# Настройка логирования
# Создаем логгер
logger = logging.getLogger('bot')
logger.setLevel(logging.DEBUG)

# Создаем обработчик для файла с DEBUG и INFO сообщениями
debug_handler = logging.FileHandler('debug_info.log')
debug_handler.setLevel(logging.DEBUG)
debug_formatter = logging.Formatter('%(asctime)s - %(levelname)s - %(message)s')
debug_handler.setFormatter(debug_formatter)

# Создаем фильтр, который пропускает только DEBUG и INFO сообщения
class DebugInfoFilter(logging.Filter):
    def filter(self, record):
        return record.levelno <= logging.INFO

debug_handler.addFilter(DebugInfoFilter())
logger.addHandler(debug_handler)

# Создаем обработчик для ошибок (WARNING, ERROR, CRITICAL)
error_handler = logging.FileHandler('error.log')
error_handler.setLevel(logging.WARNING)
error_formatter = logging.Formatter('%(asctime)s - %(levelname)s - %(message)s')
error_handler.setFormatter(error_formatter)
logger.addHandler(error_handler)

# Глобальные переменные для управления процессом проверки
CURRENT_CHECK_TASK = None
STOP_CHECKING_FLAG = False

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
    logger.info(f"Пользователь {message.from_user.id} запустил бота")
    await message.answer("Выберите действие:", reply_markup=get_main_keyboard())


@router.message(F.text == "✅ Добавить канал для проверки")
async def add_channel_command(message: Message, state: FSMContext):
    logger.info(f"Пользователь {message.from_user.id} выбрал добавление канала")
    await message.answer(
        "Отправьте ссылку на канал (например: @channel_name или https://t.me/channel_name ):",
        reply_markup=ReplyKeyboardRemove(),
    )
    await state.set_state(ChannelStates.waiting_for_channel)


@router.message(ChannelStates.waiting_for_channel)
async def process_channel_link(message: Message, state: FSMContext):
    try:
        channel_link = message.text.strip()
        logger.info(f"Пользователь {message.from_user.id} добавляет канал: {channel_link}")
        await state.update_data(channel_link=channel_link)
        success = await add_channel(channel_link, source="user")
        if success:
            logger.info(f"Канал {channel_link} успешно добавлен")
            await state.set_state(ChannelStates.choosing_action)
            await message.answer(
                f"✅ Канал {channel_link} добавлен для мониторинга!",
                reply_markup=get_main_keyboard(),
            )
            await message.answer(
                "Выберите действие:", reply_markup=parse_channel_keyboard
            )
        else:
            logger.warning(f"Не удалось добавить канал {channel_link}")
            await message.answer(
                "❌ Не удалось добавить канал. Проверьте формат ссылки.",
                reply_markup=get_main_keyboard(),
            )
            await state.clear()
    except Exception as e:
        logger.error(f"Ошибка при добавлении канала: {str(e)}")
        await message.answer(f"❌ Ошибка: {str(e)}", reply_markup=get_main_keyboard())
        await state.clear()


@router.callback_query(ChannelStates.choosing_action)
async def process_channel_action(callback_query: CallbackQuery, state: FSMContext):
    field = callback_query.data.strip()
    logger.debug(f"Выбрано действие: {field}")
    match field:
        case "inplace_parse_channel":
            data = await state.get_data()
            channel_link = data.get("channel_link")
            logger.info(f"Начинаю парсинг канала: {channel_link}")
            total_saved = await parse_channel(channel_link, limit=10)
            logger.info(f"Парсинг канала {channel_link} завершен. Сохранено постов: {total_saved}")
            await callback_query.message.answer(
                f"✅ Парсинг завершён. Сохранено постов: {total_saved}"
            )
            await callback_query.answer()
        case "back_to_menu":
            logger.debug("Возврат в главное меню")
            await callback_query.message.answer(
                f"Выберите действие:", reply_markup=get_main_keyboard()
            )
        case _:
            logger.warning(f"Неизвестное действие: {field}")
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
    logger.info(f"Пользователь {message.from_user.id} выбрал парсинг постов")
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
    logger.info(f"Пользователь {message.from_user.id} выбрал парсинг последних 50 постов")
    await message.answer("🔍 Подключаюсь к Telegram для парсинга последних постов...")
    try:
        total_saved = await parse_all_active_channels(limit_per_channel=50)
        logger.info(f"Парсинг завершен. Сохранено постов: {total_saved}")
        if total_saved > 0:
            await message.answer(f"✅ Парсинг завершён. Сохранено постов: {total_saved}", 
                                reply_markup=get_main_keyboard())
        else:
            await message.answer("ℹ️ Новых постов для сохранения не найдено.", 
                                reply_markup=get_main_keyboard())
    except Exception as e:
        logger.error(f"Ошибка при выполнении парсинга: {str(e)}")
        await message.answer("❗ Произошла ошибка при парсинге каналов.", 
                            reply_markup=get_main_keyboard())


@router.message(F.text == "📅 За период")
async def parse_by_period(message: Message):
    logger.info(f"Пользователь {message.from_user.id} выбрал парсинг за период")
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
    
    logger.info(f"Пользователь {message.from_user.id} выбрал парсинг за {months} месяцев")
    await message.answer(f"🔍 Начинаю парсинг за последние {months} месяца(ев)...")
    try:
        total_saved = await parse_all_active_channels(months=months)
        logger.info(f"Парсинг за {months} месяцев завершен. Сохранено постов: {total_saved}")
        if total_saved > 0:
            await message.answer(f"✅ Парсинг завершён. Сохранено постов: {total_saved}", 
                                reply_markup=get_main_keyboard())
        else:
            await message.answer("ℹ️ Новых постов для сохранения не найдено.", 
                                reply_markup=get_main_keyboard())
    except Exception as e:
        logger.error(f"Ошибка при выполнении парсинга за {months} месяцев: {str(e)}")
        await message.answer("❗ Произошла ошибка при парсинге каналов.", 
                            reply_markup=get_main_keyboard())


@router.message(F.text == "📚 Все посты")
async def parse_all_posts(message: Message):
    logger.info(f"Пользователь {message.from_user.id} выбрал парсинг всех постов")
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
    logger.info(f"Пользователь {message.from_user.id} подтвердил полный парсинг")
    await message.answer("🔍 Начинаю полный парсинг всех каналов...")
    try:
        total_saved = await parse_all_active_channels(all_time=True)
        logger.info(f"Полный парсинг завершен. Сохранено постов: {total_saved}")
        if total_saved > 0:
            await message.answer(f"✅ Полный парсинг завершён. Сохранено постов: {total_saved}", 
                                reply_markup=get_main_keyboard())
        else:
            await message.answer("ℹ️ Новых постов для сохранения не найдено.", 
                                reply_markup=get_main_keyboard())
    except Exception as e:
        logger.error(f"Ошибка при выполнении полного парсинга: {str(e)}")
        await message.answer("❗ Произошла ошибка при парсинге каналов.", 
                            reply_markup=get_main_keyboard())


@router.message(F.text == "❌ Отмена")
async def cancel_parsing(message: Message):
    logger.info(f"Пользователь {message.from_user.id} отменил парсинг")
    await message.answer("🚫 Парсинг отменен", reply_markup=get_main_keyboard())


@router.message(F.text == "🔄 Проверить посты на м. схемы")
async def check_new_posts(message: Message, state: FSMContext):
    logger.info(f"Пользователь {message.from_user.id} запустил проверку постов")
    count = await get_unchecked_posts_count()
    logger.info(f"Найдено {count} непроверенных постов")
    
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
                logger.info("Все посты проверены")
                break
            for post_id, post_text in posts:
                if STOP_CHECKING_FLAG:
                    logger.info("Проверка постов остановлена пользователем")
                    break
                is_recipe = await check_post(post_text)
                await mark_post_as_checked(post_id, is_recipe)
                checked_count += 1
                logger.info(f"Проверено {checked_count}/{total_count} постов. Осталось: {total_count-checked_count}")
                await message.answer(
                    f"🔍 Проверено {checked_count}/{total_count} постов...",
                    reply_markup=get_stop_keyboard(),
                )
            await asyncio.sleep(1)
        if STOP_CHECKING_FLAG:
            logger.info(f"Проверка прервана. Проверено {checked_count}/{total_count} постов")
            await message.answer(
                f"⏹ Проверка прервана. Проверено {checked_count}/{total_count} постов.",
                reply_markup=get_main_keyboard(),
            )
        else:
            logger.info(f"Проверка завершена. Обработано {checked_count} постов")
            await message.answer(
                f"✅ Проверка завершена! Обработано {checked_count} постов.",
                reply_markup=get_main_keyboard(),
            )
    except Exception as e:
        logger.error(f"Ошибка при проверке постов: {str(e)}")
        await message.answer(f"❌ Ошибка при проверке: {e}")
    finally:
        global CURRENT_CHECK_TASK
        CURRENT_CHECK_TASK = None


@router.message(F.text == "🛑 Остановить проверку")
async def stop_checking(message: Message, state: FSMContext):
    logger.info(f"Пользователь {message.from_user.id} остановил проверку")
    global STOP_CHECKING_FLAG
    STOP_CHECKING_FLAG = True
    await message.answer(
        "🛑 Останавливаю проверку...", reply_markup=ReplyKeyboardRemove()
    )
    await state.clear()


@router.message(F.text == "📤 Выгрузить данные")
async def export_data(message: Message):
    logger.info(f"Пользователь {message.from_user.id} запросил выгрузку данных")
    count = await get_unchecked_posts_count()
    logger.debug(f"Количество непроверенных постов: {count}")
    if count > 0:
        file_path = await export_data_to_excel()
        logger.info(f"Данные выгружены в файл: {file_path}")
        await message.answer_document(FSInputFile(file_path), caption="📁 Ваши данные")
    else:
        await message.answer("📁 Нет данных для выгрузки")


@router.message(F.text == "🔍 Найти новые каналы")
async def handle_find_channels(message: Message):
    logger.info(f"Пользователь {message.from_user.id} запустил поиск новых каналов")
    await message.answer("🕵️‍♂️ Начинаю поиск новых каналов...")
    try:
        new_channels = await search_new_channels()
        if not new_channels:
            logger.info("Новых каналов не найдено")
            await message.answer("🤷 Новых каналов не найдено")
            return
        logger.info(f"Найдено {len(new_channels)} новых каналов")
        saved = await save_new_channels(new_channels)
        logger.info(f"Сохранено {saved} новых каналов")
        await message.answer(
            f"✅ Найдено {len(new_channels)} новых каналов\n"
            f"📥 Сохранено: {saved} каналов\n"
            f"Примеры: {', '.join(new_channels[:5])}..."
        )
    except Exception as e:
        logger.error(f"Ошибка при поиске каналов: {str(e)}")
        await message.answer(f"❌ Ошибка при поиске каналов: {str(e)}")


@router.message(F.text == "📊 Статистика")
async def show_stats(message: Message):
    logger.info(f"Пользователь {message.from_user.id} запросил статистику")
    stats = await get_stats()
    logger.debug(f"Получена статистика: {stats}")
    text = (
        f"📊 Статистика:\n"
        f"• Всего постов: {stats['total_posts']}\n"
        f"• Рецептов: {stats['recipes']}\n"
        f"• Непроверенных: {stats['unchecked']}"
    )
    await message.answer(text)


async def search_new_channels() -> List[str]:
    logger.info("Запущен поиск новых каналов")
    CHANNEL_REGEX = r"(?:https?://)?(?:t\.me/|@)([a-zA-Z0-9_]{5,32})"
    found_channels = set()

    posts = await get_posts_for_search()
    logger.debug(f"Получено {len(posts)} постов для поиска каналов")
    for (post_text,) in posts:
        if not post_text:
            continue
        matches = re.findall(CHANNEL_REGEX, post_text)
        for channel in matches:
            normalized = f"@{channel.lower()}"
            found_channels.add(normalized)
    existing_channels = await get_channel_links()
    logger.debug(f"Найдено {len(found_channels)} каналов, существующих: {len(existing_channels)}")
    
    result = [
        channel
        for channel in found_channels
        if channel not in existing_channels
        and not channel.startswith(("@durov", "@telegram"))
    ]
    logger.info(f"Найдено {len(result)} новых каналов")
    return result


@router.message(Command("blacklist"))
async def manage_blacklist(message: Message, state: FSMContext):
    logger.info(f"Пользователь {message.from_user.id} открыл управление черным списком")
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
    logger.info(f"Пользователь {message.from_user.id} запросил черный список")
    items = await get_blacklist_pat_reason()
    if not items:
        logger.info("Черный список пуст")
        await message.answer("Черный список пуст")
        return
    logger.info(f"Получено {len(items)} элементов черного списка")
    text = "🚫 Черный список:\n" + "\n".join(
        f"• {item[0]} ({item[1] or 'без указания причины'})" for item in items
    )
    await message.answer(text[:4000])


@router.message(F.text == "🔙 Назад")
async def back_to_main_menu(message: Message):
    logger.info(f"Пользователь {message.from_user.id} вернулся в главное меню")
    await message.answer("Возвращаюсь в главное меню", reply_markup=get_main_keyboard())


def setup_bot_handlers(dp: Dispatcher):
    logger.info("Настройка обработчиков бота")
    dp.include_router(router)
