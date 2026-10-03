from aiogram.types import InlineKeyboardMarkup
from aiogram.utils.keyboard import InlineKeyboardBuilder

# Категории, которые можно выбрать при добавлении задачи (/add)
CATEGORIES_MENU = {
    "deadline_move": "📅 Перенос дедлайна",
    "urgent": "🔥 Срочно написать",
    "other": "📝 Другое",
}

# Для отображения в списках и напоминаниях: меню + служебные категории
CATEGORIES = {
    **CATEGORIES_MENU,
    "calendar": "📅 Календарь",  # ставится автоматически при импорте .ics
    # старые задачи, созданные до чистки категорий
    "meeting": "📅 Календарь",
    "restore": "📝 Другое",
}


def categories_kb() -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    for key, title in CATEGORIES_MENU.items():
        builder.button(text=title, callback_data=f"cat:{key}")
    builder.button(text="◀️ Назад", callback_data="cancel")
    builder.adjust(1)
    return builder.as_markup()


def confirm_kb() -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.button(text="✅ Сохранить", callback_data="save_task")
    builder.button(text="◀️ Назад", callback_data="back_to_date")
    builder.button(text="❌ Отмена", callback_data="cancel")
    builder.adjust(1)
    return builder.as_markup()


def tasks_kb(tasks: list) -> InlineKeyboardMarkup:
    """Кнопки-номера (1, 2, 3...) по 5 в ряд. Соответствуют нумерации в тексте сообщения."""
    builder = InlineKeyboardBuilder()
    for i, t in enumerate(tasks, 1):
        mark = "✅" if t["is_done"] else ""
        builder.button(text=f"{mark}{i}", callback_data=f"task:{t['id']}")
    builder.button(text="◀️ Назад", callback_data="back_to_menu")
    n = len(tasks)
    rows = [5] * (n // 5) + ([n % 5] if n % 5 else [])
    builder.adjust(*rows, 1)
    return builder.as_markup()


def task_actions_kb(task_id: int) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.button(text="✅ Выполнено", callback_data=f"done:{task_id}")
    builder.button(text="🗑 Удалить", callback_data=f"delete:{task_id}")
    builder.button(text="◀️ Назад", callback_data="back_to_list")
    builder.adjust(2, 1)
    return builder.as_markup()


def main_menu_kb() -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.button(text="📋 Сегодня", callback_data="menu_today")
    builder.button(text="📝 Все задачи", callback_data="menu_list")
    builder.button(text="➕ Добавить задачу", callback_data="menu_add")
    builder.button(text="👤 По ученику", callback_data="menu_student")
    builder.button(text="📆 Выбрать день", callback_data="menu_day")
    builder.button(text="📅 Импорт календаря", callback_data="menu_import")
    builder.button(text="🧹 Очистить календарь", callback_data="menu_clear_calendar")
    builder.adjust(1)
    return builder.as_markup()


def clear_calendar_kb() -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.button(text="🗑 Да, удалить", callback_data="clear_calendar_yes")
    builder.button(text="❌ Отмена", callback_data="cancel")
    builder.adjust(1)
    return builder.as_markup()


def cancel_kb() -> InlineKeyboardMarkup:
    """Кнопка под вопросами, где бот ждёт текст (фамилию, дату)."""
    builder = InlineKeyboardBuilder()
    builder.button(text="❌ Отмена", callback_data="cancel")
    return builder.as_markup()


def back_menu_kb() -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.button(text="◀️ Назад", callback_data="back_to_menu")
    return builder.as_markup()
