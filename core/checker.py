import asyncio
from gigachat import GigaChat
from database.db import get_unchecked_posts, mark_post_as_checked
from config import GIGA_API_KEY

giga = GigaChat(credentials=GIGA_API_KEY)


async def check_post(text):
    try:
        response = await giga.ask(f"Это рецепт? Ответьте только 'да' или 'нет': {text[:]}")
        return response.lower().strip() == "да"
    except Exception as e:
        print(f"GigaChat error: {e}")
        return False


async def start_checking(interval=300):
    while True:
        posts = await get_unchecked_posts(limit=10)
        for post_id, text in posts:
            is_recipe = await check_post(text)
            await mark_post_as_checked(post_id, is_recipe)
        await asyncio.sleep(interval)
