from aiogram import Router, F
from aiogram.types import Message, CallbackQuery, ContentType
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from datetime import date, datetime, timedelta
import tempfile
import os

from database.db import (
    add_task, get_tasks_by_date, get_active_tasks,
    get_tasks_by_student, mark_done, get_task, delete_task
)
from keyboards.inline import (
    categories_kb, confirm_kb, tasks_kb, task_actions_kb,
    main_menu_kb, CATEGORIES
)

router = Router()

class AddTask(StatesGroup):
    category = State()
    student = State()
    description = State()
    due_date = State()
    notes = State()
    confirm = State()

class StudentSearch(StatesGroup):
    waiting_name = State()

# ====================== СЕГОДНЯ / СПИСОК ======================

async def show_today(message: Message, user_id: int):
    tasks = await get_tasks_by_date(user_id, date.today())
    if not tasks:
        await message.answer("На сегодня задач нет 🎉", reply_markup=main_menu_kb())
        return

    text = f"📋 <b>План на сегодня ({date.today().strftime('%d.%m.%Y')})</b>\n\n"
    for t in tasks:
        cat = CATEGORIES.get(t["category"], t["category"])
        text += f"• <b>{t['student_name']}</b> [{cat}]\n  {t['description']}\n\n"

    # Если текст слишком длинный — режем
    if len(text) > 4000:
        text = text[:3900] + "\n\n... (слишком много задач, показана часть)"

    await message.answer(text, reply_markup=tasks_kb(tasks[:30]))  # кнопки тоже ограничиваем

async def show_list(message: Message, user_id: int):
    tasks = await get_active_tasks(user_id)
    if not tasks:
        await message.answer("Активных задач нет.", reply_markup=main_menu_kb())
        return

    text = "📋 <b>Все активные задачи</b>\n\n"
    for t in tasks:
        cat = CATEGORIES.get(t["category"], t["category"])
        due = datetime.fromisoformat(t["due_date"]).strftime("%d.%m")
        text += f"#{t['id']} • <b>{t['student_name']}</b> [{cat}] до {due}\n  {t['description']}\n\n"

        # Как только приближаемся к лимиту — останавливаемся
        if len(text) > 3800:
            text += f"\n... и ещё {len(tasks) - tasks.index(t) - 1} задач"
            break

    await message.answer(text, reply_markup=tasks_kb(tasks[:25]))

@router.message(Command("today"))
async def cmd_today(message: Message):
    await show_today(message, message.from_user.id)

@router.message(Command("list"))
async def cmd_list(message: Message):
    await show_list(message, message.from_user.id)

# ====================== ПОИСК ПО УЧЕНИКУ ======================

@router.message(StudentSearch.waiting_name)
async def process_student_search(message: Message, state: FSMContext):
    name = message.text.strip()
    tasks = await get_tasks_by_student(message.from_user.id, name)

    if not tasks:
        await message.answer(
            f"По запросу «{name}» активных задач нет.",
            reply_markup=main_menu_kb()
        )
        await state.clear()
        return

    text = f"👤 <b>Задачи по «{name}»</b>\n\n"
    for t in tasks:
        cat = CATEGORIES.get(t["category"], t["category"])
        due = datetime.fromisoformat(t["due_date"]).strftime("%d.%m")
        text += f"#{t['id']} [{cat}] до {due}\n  {t['description']}\n\n"

    await message.answer(text, reply_markup=tasks_kb(tasks))
    await state.clear()

@router.message(Command("student"))
async def cmd_student(message: Message, state: FSMContext):
    args = message.text.split(maxsplit=1)
    if len(args) < 2:
        await state.set_state(StudentSearch.waiting_name)
        await message.answer("Введи фамилию ученика:")
        return

    name = args[1].strip()
    tasks = await get_tasks_by_student(message.from_user.id, name)

    if not tasks:
        await message.answer(f"По ученику «{name}» активных задач нет.")
        return

    text = f"👤 <b>Задачи по {name}</b>\n\n"
    for t in tasks:
        cat = CATEGORIES.get(t["category"], t["category"])
        due = datetime.fromisoformat(t["due_date"]).strftime("%d.%m")
        text += f"#{t['id']} [{cat}] до {due}\n  {t['description']}\n\n"

    await message.answer(text, reply_markup=tasks_kb(tasks))

# ====================== ДОБАВЛЕНИЕ ЗАДАЧИ ======================

@router.message(Command("add"))
async def cmd_add(message: Message, state: FSMContext):
    await state.set_state(AddTask.category)
    await message.answer("Выбери категорию:", reply_markup=categories_kb())

@router.callback_query(AddTask.category, F.data.startswith("cat:"))
async def process_category(callback: CallbackQuery, state: FSMContext):
    category = callback.data.split(":")[1]
    await state.update_data(category=category)
    await state.set_state(AddTask.student)
    await callback.message.edit_text("Введи фамилию (или ФИО) ученика:")
    await callback.answer()

@router.message(AddTask.student)
async def process_student(message: Message, state: FSMContext):
    await state.update_data(student_name=message.text.strip())
    await state.set_state(AddTask.description)
    await message.answer("Кратко опиши задачу:")

@router.message(AddTask.description)
async def process_description(message: Message, state: FSMContext):
    await state.update_data(description=message.text.strip())
    await state.set_state(AddTask.due_date)
    await message.answer(
        "Дата (ДД.ММ или ДД.ММ.ГГГГ).\n"
        "Можно: сегодня, завтра, +3"
    )

@router.message(AddTask.due_date)
async def process_due_date(message: Message, state: FSMContext):
    text = message.text.strip().lower()
    today = date.today()

    try:
        if text == "сегодня":
            due = today
        elif text == "завтра":
            due = today + timedelta(days=1)
        elif text.startswith("+") and text[1:].isdigit():
            due = today + timedelta(days=int(text[1:]))
        else:
            parts = text.replace(",", ".").split(".")
            if len(parts) == 2:
                due = date(today.year, int(parts[1]), int(parts[0]))
                if due < today:
                    due = date(today.year + 1, int(parts[1]), int(parts[0]))
            elif len(parts) == 3:
                due = date(int(parts[2]), int(parts[1]), int(parts[0]))
            else:
                raise ValueError
    except Exception:
        await message.answer("Не понял дату. Пример: 15.10 или завтра")
        return

    await state.update_data(due_date=due.isoformat())
    await state.set_state(AddTask.notes)
    await message.answer("Дополнительные заметки (или «-» если нет):")

@router.message(AddTask.notes)
async def process_notes(message: Message, state: FSMContext):
    notes = message.text.strip()
    if notes == "-":
        notes = None
    await state.update_data(notes=notes)

    data = await state.get_data()
    cat_name = CATEGORIES.get(data["category"], data["category"])
    due = datetime.fromisoformat(data["due_date"]).strftime("%d.%m.%Y")

    text = (
        f"<b>Проверь задачу:</b>\n\n"
        f"Ученик: <b>{data['student_name']}</b>\n"
        f"Категория: {cat_name}\n"
        f"Описание: {data['description']}\n"
        f"Дата: {due}\n"
        f"Заметки: {notes or '—'}"
    )
    await state.set_state(AddTask.confirm)
    await message.answer(text, reply_markup=confirm_kb())

@router.callback_query(AddTask.confirm, F.data == "save_task")
async def save_task(callback: CallbackQuery, state: FSMContext):
    data = await state.get_data()
    task_id = await add_task(
        user_id=callback.from_user.id,
        student_name=data["student_name"],
        category=data["category"],
        description=data["description"],
        due_date=date.fromisoformat(data["due_date"]),
        notes=data.get("notes")
    )
    await state.clear()
    await callback.message.edit_text(
        f"✅ Задача #{task_id} сохранена!",
        reply_markup=main_menu_kb()
    )
    await callback.answer()

@router.callback_query(F.data == "back_to_notes")
async def back_to_notes(callback: CallbackQuery, state: FSMContext):
    await state.set_state(AddTask.notes)
    await callback.message.edit_text("Дополнительные заметки (или «-» если нет):")
    await callback.answer()

# ====================== ДЕЙСТВИЯ С ЗАДАЧЕЙ ======================

@router.callback_query(F.data.startswith("task:"))
async def show_task(callback: CallbackQuery):
    task_id = int(callback.data.split(":")[1])
    task = await get_task(callback.from_user.id, task_id)
    if not task:
        await callback.answer("Задача не найдена", show_alert=True)
        return

    cat = CATEGORIES.get(task["category"], task["category"])
    due = datetime.fromisoformat(task["due_date"]).strftime("%d.%m.%Y")
    status = "✅ Выполнено" if task["is_done"] else "⬜ Активна"

    text = (
        f"<b>Задача #{task['id']}</b>\n\n"
        f"Ученик: <b>{task['student_name']}</b>\n"
        f"Категория: {cat}\n"
        f"Описание: {task['description']}\n"
        f"Дата: {due}\n"
        f"Статус: {status}\n"
        f"Заметки: {task['notes'] or '—'}"
    )
    await callback.message.edit_text(text, reply_markup=task_actions_kb(task_id))
    await callback.answer()

@router.callback_query(F.data.startswith("done:"))
async def done_callback(callback: CallbackQuery):
    task_id = int(callback.data.split(":")[1])
    ok = await mark_done(callback.from_user.id, task_id)
    if ok:
        await callback.message.edit_text(
            f"✅ Задача #{task_id} выполнена.",
            reply_markup=main_menu_kb()
        )
    else:
        await callback.answer("Задача не найдена", show_alert=True)
    await callback.answer()

@router.callback_query(F.data.startswith("delete:"))
async def delete_callback(callback: CallbackQuery):
    task_id = int(callback.data.split(":")[1])
    ok = await delete_task(callback.from_user.id, task_id)
    if ok:
        await callback.message.edit_text(
            f"🗑 Задача #{task_id} удалена.",
            reply_markup=main_menu_kb()
        )
    else:
        await callback.answer("Задача не найдена", show_alert=True)
    await callback.answer()

@router.callback_query(F.data == "back_to_list")
async def back_to_list(callback: CallbackQuery):
    await show_list(callback.message, callback.from_user.id)
    await callback.answer()

# ====================== ИМПОРТ .ICS ======================

@router.message(F.document)
async def handle_ics(message: Message):
    doc = message.document
    if not doc.file_name or not doc.file_name.lower().endswith(".ics"):
        await message.answer("Нужен файл с расширением .ics")
        return

    status_msg = await message.answer("Читаю календарь...")

    file = await message.bot.get_file(doc.file_id)
    with tempfile.NamedTemporaryFile(delete=False, suffix=".ics") as tmp:
        await message.bot.download_file(file.file_path, tmp.name)
        tmp_path = tmp.name

    try:
        from icalendar import Calendar
        from datetime import timezone

        with open(tmp_path, "rb") as f:
            cal = Calendar.from_ical(f.read())

        events = []
        today = date.today()
        limit = today + timedelta(days=30)

        for component in cal.walk():
            if component.name != "VEVENT":
                continue

            summary = str(component.get("summary", "Без названия")).strip()
            dtstart = component.get("dtstart")
            if not dtstart:
                continue

            raw = dtstart.dt

            # Приводим к date
            if isinstance(raw, datetime):
                if raw.tzinfo is not None:
                    raw = raw.astimezone(timezone.utc).replace(tzinfo=None)
                event_date = raw.date()
            elif isinstance(raw, date):
                event_date = raw
            else:
                continue

            if today <= event_date <= limit:
                events.append((event_date, summary))

        if not events:
            await status_msg.edit_text("В календаре нет событий на ближайшие 30 дней.")
            return

        # Убираем дубликаты
        events = list(set(events))
        events.sort()

        created = 0
        for event_date, summary in events:
            await add_task(
                user_id=message.from_user.id,
                student_name="Из календаря",
                category="meeting",
                description=summary,
                due_date=event_date,
                notes="Импортировано из .ics"
            )
            created += 1

        text = f"✅ Создано задач: <b>{created}</b>\n\n"
        text += "Ближайшие события:\n"
        for d, s in events[:15]:
            text += f"• {d.strftime('%d.%m')} — {s}\n"
        if len(events) > 15:
            text += f"\n...и ещё {len(events) - 15}"

        await status_msg.edit_text(text, reply_markup=main_menu_kb())

    except Exception as e:
        await status_msg.edit_text(f"Ошибка при чтении календаря:\n<code>{e}</code>")
    finally:
        try:
            os.unlink(tmp_path)
        except:
            pass
