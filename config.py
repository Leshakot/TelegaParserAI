import os
from dotenv import load_dotenv

load_dotenv()

TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")

TELEGRAM_API_ID = int(os.getenv("TELEGRAM_API_ID"))
TELEGRAM_API_HASH = os.getenv("TELEGRAM_API_HASH")
TELEGRAM_PHONE = os.getenv("TELEGRAM_PHONE")

AUTHORIZATION_KEY = os.getenv("AUTHORIZATION_KEY")
GIGACHAT_API_KEY = os.getenv("GIGACHAT_API_KEY")

PARSE_INTERVAL = 3600
CHECK_INTERVAL = os.getenv("50")
FIND_INTERVAL = os.getenv("50")
MAX_POSTS_PER_CHANNEL = 1000

# Список каналов для парсинга
CHANNELS_TO_PARSE = [
    "https://t.me/smartmarket_community",
    "https://t.me/fa_electronics"
]
# Список триггерных слов (можно расширять)
TRIGGER_WORDS = [
    "выигрыш", "лотерея", "инвестиции", "быстрый заработок",
    "пассивный доход", "биткоин", "криптовалюта", "форекс", "ставки",
    "пирамида", "обман", "мошенничество", "легкие деньги"
]
