import html
import logging
from datetime import datetime

import pytz
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger
from aiogram import Bot

from database.db import get_tasks_by_date, get_all_users
from keyboards.inline import CATEGORIES
from config import GOALS_REMINDER, STUDENTS_REMINDER

moscow = pytz.timezone("Europe/Moscow")
SKIP_NAMES = {"из календаря", "календарь", "-"}
CALENDAR_CATEGORIES = {"calendar", "meeting"}
MAX_LEN = 3800  # запас до лимита телеграма в 4096


def is_student_task(t: dict) -> bool:
    """Задача про конкретного ученика (не событие из календаря)."""
    name = (t["student_name"] or "-").strip().lower()
    return name not in SKIP_NAMES and t["category"] not in CALENDAR_CATEGORIES


def build_text(title: str, tasks: list, empty_text: str) -> str:
    text = f"{title}\n\n"
    if not tasks:
        return text + empty_text

    shown = 0
    for t in tasks:
        cat = html.escape(str(CATEGORIES.get(t["category"], t["category"])))
        name = html.escape(t["student_name"] or "-")
        desc = (t["description"] or "").strip()
        tail = f"\n  {html.escape(desc)}\n\n" if desc else "\n"
        line = f"• <b>{name}</b> [{cat}]{tail}"
        if len(text) + len(line) > MAX_LEN:
            break
        text += line
        shown += 1

    if shown < len(tasks):
        text += f"...и ещё {len(tasks) - shown} задач"
    return text


async def broadcast(bot: Bot, title: str, empty_text: str, only_students: bool):
    """Шлёт каждому пользователю его невыполненные задачи на СЕГОДНЯ (по Москве)."""
    today = datetime.now(moscow).date()
    full_title = title.format(date=today.strftime("%d.%m"))

    for user_id in await get_all_users():
        try:
            tasks = await get_tasks_by_date(user_id, today)
            if only_students:
                tasks = [t for t in tasks if is_student_task(t)]
            await bot.send_message(user_id, build_text(full_title, tasks, empty_text))
        except Exception:
            logging.exception("Не удалось отправить напоминание %s", user_id)


async def send_goals_reminder(bot: Bot):
    """Утро: все задачи на сегодня (ученики и события из календаря)."""
    await broadcast(
        bot,
        f"🎯 <b>{GOALS_REMINDER} — План на сегодня ({{date}})</b>",
        "На сегодня задач нет.",
        only_students=False,
    )


async def send_students_reminder(bot: Bot):
    """Вечер: только задачи по ученикам на сегодня."""
    await broadcast(
        bot,
        f"👥 <b>{STUDENTS_REMINDER} — Задачи по ученикам на сегодня ({{date}})</b>",
        "На сегодня задач по ученикам нет.",
        only_students=True,
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
