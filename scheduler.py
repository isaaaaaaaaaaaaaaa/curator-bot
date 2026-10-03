import html
import logging
from datetime import datetime

import pytz
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger
from aiogram import Bot

from database.db import get_tasks_by_date, get_overdue_tasks, get_all_users
from keyboards.inline import CATEGORIES
from config import GOALS_REMINDER, STUDENTS_REMINDER

moscow = pytz.timezone("Europe/Moscow")
SKIP_NAMES = {"из календаря", "календарь", "-"}
CALENDAR_CATEGORIES = {"calendar", "meeting"}
MAX_LEN = 3800  # запас до лимита телеграма в 4096


def is_student_task(t: dict) -> bool:
    """Задача про конкретного ученика (не событие из календаря)."""
    name = (t["student_name"] or "-").strip().lower()
    imported = "импортировано из .ics" in (t.get("notes") or "").lower()
    return name not in SKIP_NAMES and t["category"] not in CALENDAR_CATEGORIES and not imported


def fmt_due(due) -> str:
    # "2026-10-05" -> "05.10"
    if not due or len(due) < 10:
        return "?"
    return f"{due[8:10]}.{due[5:7]}"


def task_line(t: dict, with_due: bool = False) -> str:
    cat = html.escape(str(CATEGORIES.get(t["category"], t["category"])))
    name = html.escape(t["student_name"] or "-")
    due = f" до {fmt_due(t['due_date'])}" if with_due else ""
    desc = (t["description"] or "").strip()
    tail = f"\n  {html.escape(desc)}\n\n" if desc else "\n"
    return f"• <b>{name}</b> [{cat}]{due}{tail}"


def fill(head: str, lines: list, limit: int) -> str:
    """Добавляет строки, пока влезает в limit, и пишет сколько не поместилось."""
    text = head
    for i, line in enumerate(lines):
        if len(text) + len(line) > limit:
            return text + f"...и ещё {len(lines) - i} задач\n\n"
        text += line
    return text


def build_text(title: str, tasks: list, empty_text: str, overdue: list = ()) -> str:
    # если есть просрочка, оставляем ей место, чтобы она не отрезалась
    today_limit = MAX_LEN if not overdue else MAX_LEN * 2 // 3

    if tasks:
        text = fill(f"{title}\n\n", [task_line(t) for t in tasks], today_limit)
    else:
        text = f"{title}\n\n{empty_text}\n\n"

    if overdue:
        text = fill(
            text.rstrip() + "\n\n⚠️ <b>Просрочено</b>\n\n",
            [task_line(t, with_due=True) for t in overdue],
            MAX_LEN,
        )
    return text.rstrip()


async def broadcast(bot: Bot, title: str, empty_text: str,
                    only_students: bool, with_overdue: bool):
    """Шлёт каждому пользователю его невыполненные задачи на СЕГОДНЯ (по Москве)."""
    today = datetime.now(moscow).date()
    full_title = title.format(date=today.strftime("%d.%m"))

    for user_id in await get_all_users():
        try:
            tasks = await get_tasks_by_date(user_id, today)
            if only_students:
                tasks = [t for t in tasks if is_student_task(t)]

            overdue = []
            if with_overdue:
                # просроченные события из календаря не показываем, только задачи по ученикам
                overdue = [t for t in await get_overdue_tasks(user_id, today) if is_student_task(t)]

            await bot.send_message(user_id, build_text(full_title, tasks, empty_text, overdue))
        except Exception:
            logging.exception("Не удалось отправить напоминание %s", user_id)


async def send_goals_reminder(bot: Bot):
    """Утро: всё на сегодня (ученики и календарь) + просроченные задачи по ученикам."""
    await broadcast(
        bot,
        f"🎯 <b>{GOALS_REMINDER} — План на сегодня ({{date}})</b>",
        "На сегодня задач нет.",
        only_students=False,
        with_overdue=True,
    )


async def send_students_reminder(bot: Bot):
    """Вечер: только задачи по ученикам на сегодня."""
    await broadcast(
        bot,
        f"👥 <b>{STUDENTS_REMINDER} — Задачи по ученикам на сегодня ({{date}})</b>",
        "На сегодня задач по ученикам нет.",
        only_students=True,
        with_overdue=False,
    )


def setup_scheduler(bot: Bot):
    scheduler = AsyncIOScheduler(timezone=moscow)

    for job, time_str in (
        (send_goals_reminder, GOALS_REMINDER),
        (send_students_reminder, STUDENTS_REMINDER),
    ):
        hour, minute = map(int, time_str.split(":"))
        scheduler.add_job(
            job,
            # таймзона именно в триггере, иначе cron считает по UTC
            CronTrigger(hour=hour, minute=minute, timezone=moscow),
            args=[bot],
        )

    scheduler.start()

    for j in scheduler.get_jobs():
        logging.info("Джоба %s, следующий запуск: %s", j.func.__name__, j.next_run_time)

    return scheduler
