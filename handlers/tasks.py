import html
import logging
from datetime import date, datetime, timedelta
from typing import List, Optional

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
    main_menu_kb, cancel_kb, CATEGORIES
)
from ui import render, Event

router = Router()

MSK = pytz.timezone("Europe/Moscow")
MAX_LEN = 3800  # запас до лимита телеграма в 4096

# Обычный текст, не команда (чтобы /add и т.п. не съедались как "фамилия ученика")
TEXT = F.text & ~F.text.startswith("/")

DATE_PROMPT = (
    "Дата (ДД.ММ или ДД.ММ.ГГГГ).\n"
    "Можно: сегодня, завтра, +3"
)

DAY_PROMPT = (
    "Какой день показать?\n"
    "ДД.ММ или ДД.ММ.ГГГГ. Можно: сегодня, завтра, вчера, +3"
)


class AddTask(StatesGroup):
    category = State()
    student = State()
    due_date = State()
    confirm = State()


class StudentSearch(StatesGroup):
    waiting_name = State()


class DayPick(StatesGroup):
    waiting_date = State()


# ====================== ХЕЛПЕРЫ ======================

def today_msk() -> date:
    # Railway живёт по UTC, поэтому date.today() ночью (00:00-03:00 МСК) даёт вчерашнюю дату
    return datetime.now(MSK).date()


def parse_date(raw: str, for_view: bool = False) -> Optional[date]:
    """ДД.ММ, ДД.ММ.ГГГГ, сегодня, завтра, +N.
    Для просмотра дня (for_view=True) ещё работает "вчера", а ДД.ММ не перескакивает на следующий год."""
    text = (raw or "").strip().lower()
    today = today_msk()
    try:
        if text == "сегодня":
            return today
        if text == "завтра":
            return today + timedelta(days=1)
        if for_view and text == "вчера":
            return today - timedelta(days=1)
        if text.startswith("+") and text[1:].isdigit():
            return today + timedelta(days=int(text[1:]))
        parts = text.replace(",", ".").split(".")
        if len(parts) == 2:
            due = date(today.year, int(parts[1]), int(parts[0]))
            if due < today and not for_view:
                due = date(today.year + 1, int(parts[1]), int(parts[0]))
            return due
        if len(parts) == 3:
            return date(int(parts[2]), int(parts[1]), int(parts[0]))
    except (ValueError, OverflowError):
        pass
    return None


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


# ====================== СЕГОДНЯ / ДЕНЬ / СПИСОК ======================
# event: Message или CallbackQuery. Экран всегда показывается в одном сообщении-панели.

async def show_day(event: Event, day: date):
    is_today = day == today_msk()
    tasks = await get_tasks_by_date(event.from_user.id, day)
    if not tasks:
        empty = "На сегодня задач нет 🎉" if is_today else f"На {day.strftime('%d.%m.%Y')} задач нет 🎉"
        await render(event, empty, main_menu_kb())
        return

    lines = [
        f"• <b>{esc(t['student_name'])}</b> [{esc(cat_name(t))}]{desc_part(t)}"
        for t in tasks
    ]
    title = "План на сегодня" if is_today else "План на"
    text = limited(f"📋 <b>{title} ({day.strftime('%d.%m.%Y')})</b>\n\n", lines)
    await render(event, text, tasks_kb(tasks[:30]))


async def show_today(event: Event):
    await show_day(event, today_msk())


async def show_list(event: Event):
    tasks = await get_active_tasks(event.from_user.id)
    if not tasks:
        await render(event, "Активных задач нет.", main_menu_kb())
        return

    lines = [
        f"#{t['id']} • <b>{esc(t['student_name'])}</b> [{esc(cat_name(t))}] "
        f"до {fmt_date(t['due_date'])}{desc_part(t)}"
        for t in tasks
    ]
    text = limited("📋 <b>Все активные задачи</b>\n\n", lines)
    await render(event, text, tasks_kb(tasks[:25]))


@router.message(Command("today"))
async def cmd_today(message: Message, state: FSMContext):
    await state.clear()
    await show_today(message)


@router.message(Command("list"))
async def cmd_list(message: Message, state: FSMContext):
    await state.clear()
    await show_list(message)


@router.message(Command("cancel"))
async def cmd_cancel(message: Message, state: FSMContext):
    await state.clear()
    await render(message, "Отменил.\n\nМеню:", main_menu_kb())


# ====================== КОНКРЕТНЫЙ ДЕНЬ ======================

@router.message(Command("day"))
async def cmd_day(message: Message, state: FSMContext):
    args = (message.text or "").split(maxsplit=1)
    if len(args) < 2:
        await state.set_state(DayPick.waiting_date)
        await render(message, DAY_PROMPT, cancel_kb())
        return

    day = parse_date(args[1], for_view=True)
    if day is None:
        await state.set_state(DayPick.waiting_date)
        await render(message, "Не понял дату. Пример: 15.10 или завтра\n\n" + DAY_PROMPT, cancel_kb())
        return
    await state.clear()
    await show_day(message, day)


@router.message(DayPick.waiting_date, TEXT)
async def process_day(message: Message, state: FSMContext):
    day = parse_date(message.text, for_view=True)
    if day is None:
        await render(message, "Не понял дату. Пример: 15.10 или завтра\n\n" + DAY_PROMPT, cancel_kb())
        return
    await state.clear()
    await show_day(message, day)


# ====================== ПОИСК ПО УЧЕНИКУ ======================

async def show_student(event: Event, name: str):
    tasks = await get_tasks_by_student(event.from_user.id, name)
    if not tasks:
        await render(
            event,
            f"По запросу «{esc(name)}» активных задач нет.",
            main_menu_kb()
        )
        return

    lines = [
        f"#{t['id']} [{esc(cat_name(t))}] до {fmt_date(t['due_date'])}{desc_part(t)}"
        for t in tasks
    ]
    text = limited(f"👤 <b>Задачи по «{esc(name)}»</b>\n\n", lines)
    await render(event, text, tasks_kb(tasks[:25]))


@router.message(Command("student"))
async def cmd_student(message: Message, state: FSMContext):
    args = (message.text or "").split(maxsplit=1)
    if len(args) < 2:
        await state.set_state(StudentSearch.waiting_name)
        await render(message, "Введи фамилию ученика (можно часть):", cancel_kb())
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
    await render(message, "Выбери категорию:", categories_kb())


@router.callback_query(AddTask.category, F.data.startswith("cat:"))
async def process_category(callback: CallbackQuery, state: FSMContext):
    category = callback.data.split(":")[1]
    await state.update_data(category=category)
    await state.set_state(AddTask.student)
    await render(callback, "Введи фамилию (или ФИО) ученика:", cancel_kb())
    await callback.answer()


@router.message(AddTask.student, TEXT)
async def process_student(message: Message, state: FSMContext):
    await state.update_data(student_name=message.text.strip())
    await state.set_state(AddTask.due_date)
    await render(message, DATE_PROMPT, cancel_kb())


@router.message(AddTask.due_date, TEXT)
async def process_due_date(message: Message, state: FSMContext):
    due = parse_date(message.text)
    if due is None:
        await render(message, "Не понял дату. Пример: 15.10 или завтра\n\n" + DATE_PROMPT, cancel_kb())
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
    await render(message, text, confirm_kb())


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
    await render(callback, f"✅ Задача #{task_id} сохранена!", main_menu_kb())
    await callback.answer()


@router.callback_query(F.data == "back_to_date")
async def back_to_date(callback: CallbackQuery, state: FSMContext):
    await state.set_state(AddTask.due_date)
    await render(callback, DATE_PROMPT, cancel_kb())
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
    await render(callback, text, task_actions_kb(task_id))
    await callback.answer()


@router.callback_query(F.data.startswith("done:"))
async def done_callback(callback: CallbackQuery):
    task_id = int(callback.data.split(":")[1])
    ok = await mark_done(callback.from_user.id, task_id)
    if not ok:
        await callback.answer("Задача не найдена", show_alert=True)
        return

    await render(callback, f"✅ Задача #{task_id} выполнена.", main_menu_kb())
    await callback.answer()


@router.callback_query(F.data.startswith("delete:"))
async def delete_callback(callback: CallbackQuery):
    task_id = int(callback.data.split(":")[1])
    ok = await delete_task(callback.from_user.id, task_id)
    if not ok:
        await callback.answer("Задача не найдена", show_alert=True)
        return

    await render(callback, f"🗑 Задача #{task_id} удалена.", main_menu_kb())
    await callback.answer()


@router.callback_query(F.data == "back_to_list")
async def back_to_list(callback: CallbackQuery):
    await show_list(callback)
    await callback.answer()


# ====================== ИМПОРТ .ICS ======================

@router.message(F.document)
async def handle_ics(message: Message):
    doc = message.document
    if not doc.file_name or not doc.file_name.lower().endswith(".ics"):
        await render(message, "Нужен файл с расширением .ics", main_menu_kb())
        return
    if doc.file_size and doc.file_size > 5 * 1024 * 1024:
        await render(message, "Файл слишком большой (больше 5 МБ).", main_menu_kb())
        return

    try:
        from icalendar import Calendar  # должен быть в requirements.txt

        # скачиваем до render(): он удаляет сообщение с файлом из чата
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
            await render(message, "В календаре нет событий на ближайшие 30 дней.", main_menu_kb())
            return

        created = 0
        for event_date, summary in events:
            # не создаём повторно то, что уже импортировали раньше
            if await task_exists(message.from_user.id, "Из календаря", summary, event_date):
                continue
            await add_task(
                user_id=message.from_user.id,
                student_name="Из календаря",
                category="calendar",
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
            text += f"• {d.strftime('%d.%m')} — {esc(s[:60])}\n"
        if len(events) > 15:
            text += f"\n...и ещё {len(events) - 15}"

        await render(message, text, main_menu_kb())

    except Exception as e:
        logging.exception("Ошибка импорта .ics")
        await render(message, f"Ошибка при чтении календаря:\n<code>{esc(e)}</code>", main_menu_kb())
