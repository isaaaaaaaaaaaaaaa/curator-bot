import os
from dotenv import load_dotenv

load_dotenv()

BOT_TOKEN = os.getenv("BOT_TOKEN")

# Время напоминаний (Москва)
MORNING_REMINDER = "09:00"
EVENING_REMINDER = "20:00"