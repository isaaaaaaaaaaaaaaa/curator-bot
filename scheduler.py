from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger
from datetime import date
from aiogram import Bot
from database.db import get_active_tasks, get_all_users
from keyboards.inline import CATEGORIES
from config import GOALS_REMINDER, STUDENTS_REMINDER
import pytz

moscow = pytz.timezone("Europe/Moscow")

async def send_goals_reminder(bot: Bot):
    """11:00 — общие цели / план"""
    users = await get_all_users()

    for user_id in users:
        tasks = await get_active_tasks(user_id)

        if not tasks:
            text = "🎯 <b>11:00 — Общие цели</b>\n\nАктивных задач пока нет."
        else:
            text = "🎯 <b>11:00 — Общие цели / план</b>\n\n"
            for t in tasks[:20]:
                cat = CATEGORIES.get(t["category"], t["category"])
                due = t["due_date"][8:10] + "." + t["due_date"][5:7]  # ДД.ММ
                text += f"• <b>{t['student_name']}</b> [{cat}] до {due}\n  {t['description']}\n\n"

            if len(tasks) > 20:
                text += f"...и ещё {len(tasks) - 20} задач"

        try:
            await bot.send_message(user_id, text)
        except Exception as e:
            print(f"Не удалось отправить {user_id}: {e}")

async def send_students_reminder(bot: Bot):
    """21:00 — задачи по ученикам"""
    users = await get_all_users()

    for user_id in users:
        tasks = await get_active_tasks(user_id)

        # Берём только задачи, где указан конкретный ученик (не "Из календаря")
        student_tasks = [
            t for t in tasks
            if t["student_name"].lower() not in ("из календаря", "календарь", "-")
        ]

        if not student_tasks:
            text = "👥 <b>21:00 — Задачи по ученикам</b>\n\nСейчас нет активных задач по ученикам."
        else:
            text = "👥 <b>21:00 — Задачи по ученикам</b>\n\n"
            for t in student_tasks[:20]:
                cat = CATEGORIES.get(t["category"], t["category"])
                due = t["due_date"][8:10] + "." + t["due_date"][5:7]
                text += f"• <b>{t['student_name']}</b> [{cat}] до {due}\n  {t['description']}\n\n"

            if len(student_tasks) > 20:
                text += f"...и ещё {len(student_tasks) - 20} задач"

        try:
            await bot.send_message(user_id, text)
        except Exception as e:
            print(f"Не удалось отправить {user_id}: {e}")

def setup_scheduler(bot: Bot):
    scheduler = AsyncIOScheduler(timezone=moscow)

    # 11:00 — общие цели
    hour, minute = map(int, GOALS_REMINDER.split(":"))
    scheduler.add_job(
        send_goals_reminder,
        CronTrigger(hour=hour, minute=minute),
        args=[bot]
    )

    # 21:00 — задачи по ученикам
    hour, minute = map(int, STUDENTS_REMINDER.split(":"))
    scheduler.add_job(
        send_students_reminder,
        CronTrigger(hour=hour, minute=minute),
        args=[bot]
    )

    scheduler.start()
    return scheduler
