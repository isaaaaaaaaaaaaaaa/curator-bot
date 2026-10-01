import html
import logging

import pytz
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger
from aiogram import Bot

from database.db import get_active_tasks, get_all_users
from keyboards.inline import CATEGORIES
from config import GOALS_REMINDER, STUDENTS_REMINDER

moscow = pytz.timezone("Europe/Moscow")
SKIP_NAMES = {"из календаря", "календарь", "-"}
MAX_LEN = 3800  # запас до лимита телеграма в 4096


def fmt_due(due) -> str:
    # "2026-10-05" -> "05.10"
    if not due or len(due) < 10:
        return "?"
    return f"{due[8:10]}.{due[5:7]}"


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
        line = f"• <b>{name}</b> [{cat}] до {fmt_due(t['due_date'])}{tail}"
        if len(text) + len(line) > MAX_LEN:
            break
        text += line
        shown += 1

    if shown < len(tasks):
        text += f"...и ещё {len(tasks) - shown} задач"
    return text


async def broadcast(bot: Bot, make_text):
    for user_id in await get_all_users():
        try:
            tasks = await get_active_tasks(user_id)
            await bot.send_message(user_id, make_text(tasks))
        except Exception:
            logging.exception("Не удалось отправить напоминание %s", user_id)


async def send_goals_reminder(bot: Bot):
    """11:00 — общие цели / план"""
    await broadcast(bot, lambda tasks: build_text(
        f"🎯 <b>{GOALS_REMINDER} — Общие цели / план</b>",
        tasks,
        "Активных задач пока нет.",
    ))


async def send_students_reminder(bot: Bot):
    """21:00 — задачи по ученикам"""
    def make(tasks):
        # только задачи с конкретным учеником (не "Из календаря")
        student_tasks = [
            t for t in tasks
            if (t["student_name"] or "-").lower() not in SKIP_NAMES
        ]
        return build_text(
            f"👥 <b>{STUDENTS_REMINDER} — Задачи по ученикам</b>",
            student_tasks,
            "Сейчас нет активных задач по ученикам.",
        )
    await broadcast(bot, make)


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
