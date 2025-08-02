from aiogram.fsm.state import State, StatesGroup


class ChannelStates(StatesGroup):
    waiting_for_channel = State()
    choosing_action = State()


class PostCheck(StatesGroup):
    checking = State()
    processing = State()


class BlockAdd(StatesGroup):
    bane = State()    
