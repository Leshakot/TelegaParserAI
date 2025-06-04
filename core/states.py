from aiogram.fsm.state import State, StatesGroup


class ChannelStates(StatesGroup):
    waiting_for_channel = State()


class PostCheck(StatesGroup):
    checking = State()
    processing = State()
