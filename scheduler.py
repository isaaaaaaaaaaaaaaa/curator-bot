from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger
from datetime import date
from aiogram import Bot
from database.db import get_tasks_by_date, get_active_tasks, get_all_users
from keyboards.inline import CATEGORIES
from config import MORNING_REMINDER, EVENING_REMINDER
import pytz

moscow = pytz.timezone("Europe/Moscow")

async def send_daily_summary(bot: Bot, is_morning: bool = True):
    users = await get_all_users()
    title = "🌅 Доброе утро! План на сегодня:" if is_morning else "🌙 Вечерняя сводка. Что осталось на сегодня:"

    for user_id in users:
        tasks = await get_tasks_by_date(user_id, date.today())

        if not tasks:
            text = f"{title}\n\nНа сегодня задач нет 🎉"
        else:
            text = f"{title}\n\n"
            for t in tasks:
                cat = CATEGORIES.get(t["category"], t["category"])
                text += f"• <b>{t['student_name']}</b> [{cat}]\n  {t['description']}\n\n"

        # Просроченные
        all_active = await get_active_tasks(user_id)
        overdue = [t for t in all_active if date.fromisoformat(t["due_date"]) < date.today()]
        if overdue:
            text += "\n⚠️ <b>Просрочено:</b>\n"
            for t in overdue:
                text += f"• {t['student_name']} — {t['description']}\n"

        try:
            await bot.send_message(user_id, text)
        except Exception as e:
            print(f"Не удалось отправить {user_id}: {e}")

def setup_scheduler(bot: Bot):
    scheduler = AsyncIOScheduler(timezone=moscow)

    hour, minute = map(int, MORNING_REMINDER.split(":"))
    scheduler.add_job(
        send_daily_summary,
        CronTrigger(hour=hour, minute=minute),
        args=[bot, True]
    )

    hour, minute = map(int, EVENING_REMINDER.split(":"))
    scheduler.add_job(
        send_daily_summary,
        CronTrigger(hour=hour, minute=minute),
        args=[bot, False]
    )

    scheduler.start()
    return scheduler