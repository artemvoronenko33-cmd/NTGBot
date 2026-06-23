from aiogram.fsm.state import State, StatesGroup


class TopUpStates(StatesGroup):
    waiting_for_amount = State()

class WorkerStates(StatesGroup):
    waiting_for_category = State()      # Ожидание выбора категории/продукта
    waiting_for_account_name = State()  # Ожидание названия аккаунта (опционально)
    waiting_for_files = State()         # Ожидание ZIP-архива с аккаунтами
    waiting_for_metadata = State()      # Ожидание дополнительных характеристик (опционально)