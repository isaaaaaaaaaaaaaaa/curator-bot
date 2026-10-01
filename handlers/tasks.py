import html
import logging
from datetime import date, datetime, timedelta
from typing import List

import pytz
from aiogram import Router, F
from aiogram.types import Message, CallbackQuery
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup

from database.db import (
    add_task, get_tasks_by_date, get_active_tasks,
    get_tasks_by_student, mark_done, get_task, delete_task, task_exists
)
from keyboards.inline import (
    categories_kb, confirm_kb, tasks_kb, task_actions_kb,
    main_menu_kb, CATEGORIES
)

router = Router()

MSK = pytz.timezone("Europe/Moscow")
MAX_LEN = 3800  # запас до лимита телеграма в 4096

# Обычный текст, не команда (чтобы /add и т.п. не съедались как "фамилия ученика")
TEXT = F.text & ~F.text.startswith("/")

DATE_PROMPT = (
    "Дата (ДД.ММ или ДД.ММ.ГГГГ).\n"
    "Можно: сегодня, завтра, +3"
)


class AddTask(StatesGroup):
    category = State()
    student = State()
    due_date = State()
    confirm = State()


class StudentSearch(StatesGroup):
    waiting_name = State()


# ====================== ХЕЛПЕРЫ ======================

def today_msk() -> date:
    # Railway живёт по UTC, поэтому date.today() ночью (00:00-03:00 МСК) даёт вчерашнюю дату
    return datetime.now(MSK).date()


def esc(value) -> str:
    """Экранируем пользовательский текст, потому что бот в ParseMode.HTML."""
    return html.escape(str(value)) if value is not None else ""


def cat_name(task: dict) -> str:
    return str(CATEGORIES.get(task["category"], task["category"]))


def desc_part(task: dict) -> str:
    """Описание показываем, только если оно есть (у новых задач его нет, у старых и из .ics есть)."""
    d = (task.get("description") or "").strip()
    return f"\n  {esc(d)}\n\n" if d else "\n"


def fmt_date(iso, fmt: str = "%d.%m") -> str:
    try:
        return datetime.fromisoformat(iso).strftime(fmt)
    except (TypeError, ValueError):
        return "?"


def limited(head: str, lines: List[str]) -> str:
    """Склеивает строки, пока влезает в лимит телеграма, и пишет сколько не поместилось."""
    text = head
    for i, line in enumerate(lines):
        if len(text) + len(line) > MAX_LEN:
            return text + f"...и ещё {len(lines) - i}"
        text += line
    return text


# ====================== СЕГОДНЯ / СПИСОК ======================

async def show_today(message: Message, user_id: int):
    today = today_msk()
    tasks = await get_tasks_by_date(user_id, today)
    if not tasks:
        await message.answer("На сегодня задач нет 🎉", reply_markup=main_menu_kb())
        return

    lines = [
        f"• <b>{esc(t['student_name'])}</b> [{esc(cat_name(t))}]{desc_part(t)}"
        for t in tasks
    ]
    text = limited(f"📋 <b>План на сегодня ({today.strftime('%d.%m.%Y')})</b>\n\n", lines)
    await message.answer(text, reply_markup=tasks_kb(tasks[:30]))


async def show_list(message: Message, user_id: int):
    tasks = await get_active_tasks(user_id)
    if not tasks:
        await message.answer("Активных задач нет.", reply_markup=main_menu_kb())
        return

    lines = [
        f"#{t['id']} • <b>{esc(t['student_name'])}</b> [{esc(cat_name(t))}] "
        f"до {fmt_date(t['due_date'])}{desc_part(t)}"
        for t in tasks
    ]
    text = limited("📋 <b>Все активные задачи</b>\n\n", lines)
    await message.answer(text, reply_markup=tasks_kb(tasks[:25]))


@router.message(Command("today"))
async def cmd_today(message: Message):
    await show_today(message, message.from_user.id)


@router.message(Command("list"))
async def cmd_list(message: Message):
    await show_list(message, message.from_user.id)


@router.message(Command("cancel"))
async def cmd_cancel(message: Message, state: FSMContext):
    await state.clear()
    await message.answer("Отменил.", reply_markup=main_menu_kb())


# ====================== ПОИСК ПО УЧЕНИКУ ======================

async def show_student(message: Message, name: str):
    tasks = await get_tasks_by_student(message.from_user.id, name)
    if not tasks:
        await message.answer(
            f"По запросу «{esc(name)}» активных задач нет.",
            reply_markup=main_menu_kb()
        )
        return

    lines = [
        f"#{t['id']} [{esc(cat_name(t))}] до {fmt_date(t['due_date'])}{desc_part(t)}"
        for t in tasks
    ]
    text = limited(f"👤 <b>Задачи по «{esc(name)}»</b>\n\n", lines)
    await message.answer(text, reply_markup=tasks_kb(tasks[:25]))


@router.message(Command("student"))
async def cmd_student(message: Message, state: FSMContext):
    args = (message.text or "").split(maxsplit=1)
    if len(args) < 2:
        await state.set_state(StudentSearch.waiting_name)
        await message.answer("Введи фамилию ученика:")
        return

    await state.clear()
    await show_student(message, args[1].strip())


@router.message(StudentSearch.waiting_name, TEXT)
async def process_student_search(message: Message, state: FSMContext):
    await state.clear()
    await show_student(message, message.text.strip())


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


@router.message(AddTask.student, TEXT)
async def process_student(message: Message, state: FSMContext):
    await state.update_data(student_name=message.text.strip())
    await state.set_state(AddTask.due_date)
    await message.answer(DATE_PROMPT)


@router.message(AddTask.due_date, TEXT)
async def process_due_date(message: Message, state: FSMContext):
    text = message.text.strip().lower()
    today = today_msk()

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
    data = await state.get_data()
    cat = esc(CATEGORIES.get(data["category"], data["category"]))

    text = (
        f"<b>Проверь задачу:</b>\n\n"
        f"Ученик: <b>{esc(data['student_name'])}</b>\n"
        f"Категория: {cat}\n"
        f"Дата: {fmt_date(data['due_date'], '%d.%m.%Y')}"
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
        description="",  # колонка NOT NULL, поэтому пустая строка
        due_date=date.fromisoformat(data["due_date"]),
        notes=None
    )
    await state.clear()
    await callback.message.edit_text(
        f"✅ Задача #{task_id} сохранена!",
        reply_markup=main_menu_kb()
    )
    await callback.answer()


@router.callback_query(F.data == "back_to_notes")
async def back_to_date(callback: CallbackQuery, state: FSMContext):
    # callback_data "back_to_notes" оставил как есть, чтобы не трогать клавиатуры
    await state.set_state(AddTask.due_date)
    await callback.message.edit_text(DATE_PROMPT)
    await callback.answer()


# ====================== ДЕЙСТВИЯ С ЗАДАЧЕЙ ======================

@router.callback_query(F.data.startswith("task:"))
async def show_task(callback: CallbackQuery):
    task_id = int(callback.data.split(":")[1])
    task = await get_task(callback.from_user.id, task_id)
    if not task:
        await callback.answer("Задача не найдена", show_alert=True)
        return

    status = "✅ Выполнено" if task["is_done"] else "⬜ Активна"

    text = (
        f"<b>Задача #{task['id']}</b>\n\n"
        f"Ученик: <b>{esc(task['student_name'])}</b>\n"
        f"Категория: {esc(cat_name(task))}\n"
        f"Дата: {fmt_date(task['due_date'], '%d.%m.%Y')}\n"
        f"Статус: {status}"
    )
    if (task["description"] or "").strip():
        text += f"\nОписание: {esc(task['description'])}"
    if task["notes"]:
        text += f"\nЗаметки: {esc(task['notes'])}"
    await callback.message.edit_text(text, reply_markup=task_actions_kb(task_id))
    await callback.answer()


@router.callback_query(F.data.startswith("done:"))
async def done_callback(callback: CallbackQuery):
    task_id = int(callback.data.split(":")[1])
    ok = await mark_done(callback.from_user.id, task_id)
    if not ok:
        await callback.answer("Задача не найдена", show_alert=True)
        return

    await callback.message.edit_text(
        f"✅ Задача #{task_id} выполнена.",
        reply_markup=main_menu_kb()
    )
    await callback.answer()


@router.callback_query(F.data.startswith("delete:"))
async def delete_callback(callback: CallbackQuery):
    task_id = int(callback.data.split(":")[1])
    ok = await delete_task(callback.from_user.id, task_id)
    if not ok:
        await callback.answer("Задача не найдена", show_alert=True)
        return

    await callback.message.edit_text(
        f"🗑 Задача #{task_id} удалена.",
        reply_markup=main_menu_kb()
    )
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
    if doc.file_size and doc.file_size > 5 * 1024 * 1024:
        await message.answer("Файл слишком большой (больше 5 МБ).")
        return

    status_msg = await message.answer("Читаю календарь...")

    try:
        from icalendar import Calendar  # должен быть в requirements.txt

        buf = await message.bot.download(doc)
        cal = Calendar.from_ical(buf.read())

        today = today_msk()
        limit = today + timedelta(days=30)
        found = set()  # set сразу убирает дубли внутри файла

        for component in cal.walk():
            if component.name != "VEVENT":
                continue

            summary = str(component.get("summary", "Без названия")).strip()
            dtstart = component.get("dtstart")
            if not dtstart:
                continue

            raw = dtstart.dt

            # Приводим к дате. Время с таймзоной переводим в Москву,
            # иначе событие в 01:00 МСК уехало бы на предыдущий день
            if isinstance(raw, datetime):
                if raw.tzinfo is not None:
                    raw = raw.astimezone(MSK)
                event_date = raw.date()
            elif isinstance(raw, date):
                event_date = raw
            else:
                continue

            if today <= event_date <= limit:
                found.add((event_date, summary))

        events = sorted(found)
        if not events:
            await status_msg.edit_text("В календаре нет событий на ближайшие 30 дней.")
            return

        created = 0
        for event_date, summary in events:
            # не создаём повторно то, что уже импортировали раньше
            if await task_exists(message.from_user.id, "Из календаря", summary, event_date):
                continue
            await add_task(
                user_id=message.from_user.id,
                student_name="Из календаря",
                category="meeting",
                description=summary,
                due_date=event_date,
                notes="Импортировано из .ics"
            )
            created += 1

        skipped = len(events) - created
        text = f"✅ Создано задач: <b>{created}</b>\n"
        if skipped:
            text += f"Уже были в базе: {skipped}\n"
        text += "\nБлижайшие события:\n"
        for d, s in events[:15]:
            text += f"• {d.strftime('%d.%m')} — {esc(s)}\n"
        if len(events) > 15:
            text += f"\n...и ещё {len(events) - 15}"

        await status_msg.edit_text(text, reply_markup=main_menu_kb())

    except Exception as e:
        logging.exception("Ошибка импорта .ics")
        await status_msg.edit_text(f"Ошибка при чтении календаря:\n<code>{esc(e)}</code>")
