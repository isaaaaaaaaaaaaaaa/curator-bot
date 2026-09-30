from aiogram import Router, F
from aiogram.types import Message, CallbackQuery
from aiogram.filters import CommandStart, Command
from database.db import add_user
from keyboards.inline import main_menu_kb

router = Router()

@router.message(CommandStart())
async def cmd_start(message: Message):
    await add_user(
        user_id=message.from_user.id,
        full_name=message.from_user.full_name,
        username=message.from_user.username
    )
    await message.answer(
        "Привет! Я бот-куратор.\n\n"
        "Выбери действие:",
        reply_markup=main_menu_kb()
    )

@router.message(Command("help"))
async def cmd_help(message: Message):
    await cmd_start(message)

@router.message(Command("menu"))
async def cmd_menu(message: Message):
    await message.answer("Меню:", reply_markup=main_menu_kb())