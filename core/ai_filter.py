import aiohttp
import asyncio
import json
import uuid
import time
import ssl
from pathlib import Path

# from database.db_commands import get_unchecked_posts, mark_post_as_checked
# from config import GIGACHAT_API_KEY
import os
from dotenv import load_dotenv

load_dotenv()

GIGACHAT_API_KEY = os.getenv("GIGACHAT_API_KEY")

# Кэш токена
token_cache = {"access_token": None, "expires_at": 0}

# Путь к SSL-сертификату
cert_path = 'russian_trusted_root_ca.cer'


def create_ssl_contex():
    ssl_context = ssl.create_default_context(cafile=cert_path)
    return ssl_context


def generate_rquid():
    """Генерирует корректный RqUID в формате UUID4"""
    return str(uuid.uuid4())


async def get_gigachat_token():
    """Исправленная версия с правильной настройкой SSL"""
    print("get token")
    if token_cache["access_token"] and time.time() < token_cache["expires_at"]:
        return token_cache["access_token"]

    # Создаем SSL контекст с нашим сертификатом
    ssl_context = create_ssl_contex()

    url = "https://ngw.devices.sberbank.ru:9443/api/v2/oauth"
    headers = {
        "Content-Type": "application/x-www-form-urlencoded",
        "Accept": "application/json",
        "RqUID": str(uuid.uuid4()),
        "Authorization": f"Basic {GIGACHAT_API_KEY}",
    }

    try:
        async with aiohttp.ClientSession() as session:
            async with session.post(
                url,
                headers=headers,
                data={"scope": "GIGACHAT_API_PERS"},
                ssl=False,  # Передаем SSL контекст
            ) as response:
                if response.status == 200:
                    token_data = await response.json()
                    token_cache.update(
                        {
                            "access_token": token_data["access_token"],
                            "expires_at": time.time() + 1800,
                        }
                    )
                    print("access token")
                    return token_cache["access_token"]
                print(f"Ошибка HTTP: {response.status}")
    except Exception as e:
        print("1st error")
        print(f"Ошибка соединения: {e}")
    return None


async def analyze_post_with_gigachat(post_text: str) -> str:
    """Асинхронный анализ текста с исправленным SSL"""
    print("in analyze")
    token = await get_gigachat_token()
    print("cont analyze")
    if not token:
        print("no token")
        return "Ошибка: не удалось получить токен"

    # Создаем SSL контекст для основного запроса
    ssl_context = create_ssl_contex()

    url = "https://gigachat.devices.sberbank.ru/api/v1/chat/completions"
    payload = {
        "model": "GigaChat",
        "messages": [
            {
                "role": "system",
                "content": """
                        Ты являешься экспертом по анализу текста и выявлению потенциально опасного контента. Проанализируй следующий текст поста и определи, содержит ли он признаки, которые могут быть связаны с мошенническими или манипулятивными схемами.
                        В переданном тексте могут быть попытки обмана или манипуляции над человеком или истории очевидцев

                        Вот критерии анализа:
                        1. Обещание выгод/подарков за выполнение действий (например, переводы, заполнение форм).
                        2. Подозрительные ссылки или призывы предоставлять личные данные.
                        3. Использование слов: "бесплатно", "срочно", "ограниченное время", "только сегодня", "кэшбэк".
                        4. Стиль текста: манипулятивный, создающий ложное доверие к источнику.
                        5. Призыв к действию без ясного и проверенного источника.

                        Если такие признаки найдены, перечисли их и укажи уровень риска (низкий, средний, высокий)
                    """,
            },
            {
                "role": "user",
                "content": f'Определи есть в тексте потенциальные схемы для заработка или получения бонусов или попытка обмана человека или история об обмане, ответь да или нет, пример текста:  "{post_text[:4000]}"',
            },
        ],
        "temperature": 0.1,
    }

    try:
        print("start session")
        async with aiohttp.ClientSession() as session:
            async with session.post(
                url,
                json=payload,
                headers={
                    "Authorization": f"Bearer {token}",
                    "Content-Type": "application/json",
                },
                ssl=False,
                timeout=aiohttp.ClientTimeout(total=30),
            ) as response:
                if response.status == 200:
                    data = await response.json()
                    return data["choices"][0]["message"]["content"].strip()
                return f"Ошибка API: {response.status}"

    except Exception as e:
        print(f"Ошибка запроса: {e}")
        return "Ошибка соединения"


async def check_post(post_text: str) -> bool:
    """Проверяет, содержит ли текст мошенническую схему"""
    try:
        print("in check")
        response = await analyze_post_with_gigachat(post_text)
        print(response)
        return response.lower() == "да"
    except Exception as e:
        print(f"Ошибка при проверке поста: {e}")
        return False


# async def start_checking(interval: int = 300):
#     """Основной цикл проверки постов"""
#     while True:
#         try:
#             posts = await get_unchecked_posts(limit=10)
#             for post_id, post_text in posts:
#                 print(post_id, post_text)
#                 is_scam = await check_post(post_text)
#                 await mark_post_as_checked(post_id, is_scam)

#                 # Небольшая пауза между запросами
#                 await asyncio.sleep(1)

#         except Exception as e:
#             print(f"Критическая ошибка в цикле проверки: {e}")

#         await asyncio.sleep(interval)


# Пример запуска (для тестирования)
# async def test_check():
#     test_text = "Это тестовый текст с предложением быстрого обогащения"
#     result = await check_post(test_text)
#     print(f"Результат проверки: {'Мошенничество' if result else 'Безопасно'}")
#
#
# if __name__ == "__main__":
#     asyncio.run(test_check())


if __name__ == "__main__":
    asyncio.run(
        check_post(
            """ 
            
            """
        )
    )
s = """
        Схема для заработка создаем три аккаунта и переводим денбги на них, с помощью фейкового эмейла пишем в поддержку
        """
