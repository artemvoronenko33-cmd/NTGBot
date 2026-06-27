from aiogram.fsm.state import State, StatesGroup


class TopUpStates(StatesGroup):
    """FSM для пополнения баланса"""
    waiting_for_amount = State()


class WorkerUploadStates(StatesGroup):
    """FSM для загрузки аккаунтов работником

    Навигация по категориям/продуктам через inline-кнопки (без FSM).
    FSM нужна только для ожидания ZIP-архива.
    """
    waiting_for_zip = State()