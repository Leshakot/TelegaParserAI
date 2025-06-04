from aiogram.types import ReplyKeyboardMarkup, KeyboardButton


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
