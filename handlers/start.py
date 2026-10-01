from aiogram import Router, F
from aiogram.types import Message, CallbackQuery
from aiogram.filters import CommandStart, Command
from aiogram.fsm.context import FSMContext

from database.db import add_user, count_calendar_tasks, delete_calendar_tasks
from keyboards.inline import (
    main_menu_kb, categories_kb, clear_calendar_kb, cancel_kb, back_menu_kb
)
from handlers.tasks import (
    show_today, show_list, AddTask, StudentSearch, DayPick, DAY_PROMPT
)
from ui import render

router = Router()


@router.message(CommandStart())
async def cmd_start(message: Message, state: FSMContext):
    await state.clear()
    await add_user(
        user_id=message.from_user.id,
        full_name=message.from_user.full_name,
        username=message.from_user.username
    )
    # fresh=True: меню приезжает вниз чата, а старая панель удаляется
    await render(
        message,
        "Привет! Я бот-куратор.\n\nВыбери действие:",
        main_menu_kb(),
        fresh=True
    )


@router.message(Command("help"))
@router.message(Command("menu"))
async def cmd_menu(message: Message, state: FSMContext):
    await state.clear()
    await render(message, "Меню:", main_menu_kb(), fresh=True)


# ========== МЕНЮ ==========

@router.callback_query(F.data == "menu_today")
async def menu_today(callback: CallbackQuery):
    await show_today(callback)
    await callback.answer()


@router.callback_query(F.data == "menu_list")
async def menu_list(callback: CallbackQuery):
    await show_list(callback)
    await callback.answer()


@router.callback_query(F.data == "menu_add")
async def menu_add(callback: CallbackQuery, state: FSMContext):
    await state.set_state(AddTask.category)
    await render(callback, "Выбери категорию:", categories_kb())
    await callback.answer()


@router.callback_query(F.data == "menu_student")
async def menu_student(callback: CallbackQuery, state: FSMContext):
    await state.set_state(StudentSearch.waiting_name)
    await render(
        callback,
        "Введи фамилию ученика (можно часть):\n\nПример: Иванов или Ива",
        cancel_kb()
    )
    await callback.answer()


@router.callback_query(F.data == "menu_day")
async def menu_day(callback: CallbackQuery, state: FSMContext):
    await state.set_state(DayPick.waiting_date)
    await render(callback, DAY_PROMPT, cancel_kb())
    await callback.answer()


@router.callback_query(F.data == "menu_import")
async def menu_import(callback: CallbackQuery):
    await render(
        callback,
        "Пришли мне файл <b>.ics</b> (календарь).\n\n"
        "Я найду события на ближайшие 30 дней и создам из них задачи.",
        back_menu_kb()
    )
    await callback.answer()


@router.callback_query(F.data == "menu_clear_calendar")
async def menu_clear_calendar(callback: CallbackQuery):
    count = await count_calendar_tasks(callback.from_user.id)
    if count == 0:
        await render(callback, "Задач из календаря нет, чистить нечего.", main_menu_kb())
    else:
        await render(
            callback,
            f"Удалить все задачи из календаря ({count})?\n\n"
            "Удалятся и выполненные. Задачи, которые ты добавлял вручную, не тронутся.",
            clear_calendar_kb()
        )
    await callback.answer()


@router.callback_query(F.data == "clear_calendar_yes")
async def clear_calendar_yes(callback: CallbackQuery):
    deleted = await delete_calendar_tasks(callback.from_user.id)
    await render(callback, f"🗑 Удалено задач из календаря: {deleted}", main_menu_kb())
    await callback.answer()


@router.callback_query(F.data == "back_to_menu")
async def back_to_menu(callback: CallbackQuery, state: FSMContext):
    await state.clear()
    await render(callback, "Меню:", main_menu_kb())
    await callback.answer()


@router.callback_query(F.data == "cancel")
async def cancel(callback: CallbackQuery, state: FSMContext):
    await state.clear()
    await render(callback, "Отменено.\n\nМеню:", main_menu_kb())
    await callback.answer()
