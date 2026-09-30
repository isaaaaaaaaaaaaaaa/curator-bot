import os
from dotenv import load_dotenv

load_dotenv()

BOT_TOKEN = os.getenv("BOT_TOKEN")

# Время напоминаний (Москва)
GOALS_REMINDER = "11:00"      # общие цели
STUDENTS_REMINDER = "21:00"   # задачи по ученикам
