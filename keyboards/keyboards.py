from aiogram.types import (
    ReplyKeyboardMarkup,
    KeyboardButton,
    InlineKeyboardMarkup,
    InlineKeyboardButton,
)


def get_main_keyboard():
    return ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text="✅ Добавить канал для проверки")],
            [KeyboardButton(text="👀 Парсинг постов")],
            [KeyboardButton(text="🔄 Проверить посты на м. схемы")],
            [KeyboardButton(text="📤 Выгрузить данные")],
            [KeyboardButton(text="🔍 Найти новые каналы")],
            [KeyboardButton(text="📜 Показать черный список")],
            [KeyboardButton(text="📊 Статистика")],
        ],
        resize_keyboard=True,
    )


def get_stop_keyboard():
    return ReplyKeyboardMarkup(
        keyboard=[[KeyboardButton(text="🛑 Остановить проверку")]], resize_keyboard=True
    )


parse_channel_button = InlineKeyboardButton(
    text="👀 Парсинг постов", callback_data="inplace_parse_channel"
)
back_to_menu_button = InlineKeyboardButton(
    text="🔙 Назад", callback_data="back_to_menu"
)

parse_channel_keyboard = InlineKeyboardMarkup(
    inline_keyboard=[
        [parse_channel_button],
        [back_to_menu_button],
    ]
)
