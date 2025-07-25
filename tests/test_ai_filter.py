import pytest
import uuid
from core.ai_filter import  check_post, analyze_post_with_gigachat, get_gigachat_token, generate_rquid

test_data = [
    (
        '''
Схема для заработка создаем три аккаунта и переводим денбги на них, с помощью фейкового эмейла пишем в поддержку
        ''',
        True
    ),
    (
        '''
Погибли все пассажиры и члены экипажа. Самолет эксплуатировался почти полвека, что вновь поставило вопрос о допустимых сроках службы устаревшей советской авиатехники. В то же время замены машинам вроде Ан-24 до сих пор нет
        ''',
        False
    ),
    (
        '''
Что означает для рынка решение крупнейшего российского ретейлера остановить отгрузки продукции одного из крупнейших производителей кондитерских изделий в мире? И удастся ли сторонам договориться?
        ''',
        False
    )
]

@pytest.mark.asyncio
async def test_checking():
    for tt, t_out in test_data:
        res = await check_post(tt)
        assert res == t_out

@pytest.mark.asyncio
async def test_gigachat_analyzing():
    for tt, _ in test_data:
        res = await analyze_post_with_gigachat(tt)
        assert isinstance(res, str)
        assert len(res) < 10

@pytest.mark.asyncio
async def test_token_retrive():
    assert await get_gigachat_token()

@pytest.mark.asyncio
async def test_uUid_generation():
    _uuid = uuid.UUID(generate_rquid())
    assert isinstance(_uuid, uuid.UUID)
    assert _uuid.version == 4