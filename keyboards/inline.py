from aiogram.types import InlineKeyboardMarkup
from aiogram.utils.keyboard import InlineKeyboardBuilder

CATEGORIES = {
    "deadline_move": "📅 Перенос дедлайна",
    "urgent": "🔥 Срочно написать",
    "restore": "❤️ Восстановить жизнь",
    "meeting": "🗓 Встреча",
    "other": "📝 Другое"
}

def categories_kb() -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    for key, title in CATEGORIES.items():
        builder.button(text=title, callback_data=f"cat:{key}")
    builder.button(text="◀️ Назад", callback_data="cancel")
    builder.adjust(1)
    return builder.as_markup()

def confirm_kb() -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.button(text="✅ Сохранить", callback_data="save_task")
    builder.button(text="◀️ Назад", callback_data="back_to_notes")
    builder.button(text="❌ Отмена", callback_data="cancel")
    builder.adjust(1)
    return builder.as_markup()

def tasks_kb(tasks: list) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    for t in tasks:
        status = "✅" if t["is_done"] else "⬜"
        text = f"{status} {t['student_name'][:15]} — {t['description'][:25]}"
        builder.button(text=text, callback_data=f"task:{t['id']}")
    builder.button(text="◀️ Назад", callback_data="back_to_menu")
    builder.adjust(1)
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
    builder.button(text="👤 По студенту", callback_data="menu_student")
    builder.button(text="📅 Импорт календаря", callback_data="menu_import")
    builder.adjust(1)
    return builder.as_markup()