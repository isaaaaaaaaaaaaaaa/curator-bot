"""
Один экран = одно сообщение.

Бот держит в чате одно сообщение-«панель» и каждый раз редактирует его,
а не шлёт новое. Сообщения, которые пишет пользователь (команды, фамилии, даты),
бот удаляет, чтобы чат не зарастал.
"""
import logging
from typing import Dict, Optional, Union

from aiogram.exceptions import TelegramBadRequest
from aiogram.types import CallbackQuery, InlineKeyboardMarkup, Message

Event = Union[Message, CallbackQuery]

# chat_id -> message_id панели. Живёт в памяти: после перезапуска бота
# первое действие просто создаст новую панель.
_panels: Dict[int, int] = {}


async def _safe_delete(bot, chat_id: int, message_id: int) -> None:
    try:
        await bot.delete_message(chat_id, message_id)
    except Exception:
        pass  # уже удалено или старше 48 часов


async def _try_edit(bot, chat_id: int, message_id: int, text: str,
                    kb: Optional[InlineKeyboardMarkup]) -> bool:
    """True, если сообщение теперь показывает нужный текст."""
    try:
        await bot.edit_message_text(
            text, chat_id=chat_id, message_id=message_id, reply_markup=kb
        )
        return True
    except TelegramBadRequest as e:
        # тот же текст и кнопки: менять нечего, это не ошибка
        return "message is not modified" in str(e)
    except Exception:
        logging.exception("Не удалось отредактировать панель")
        return False


async def render(event: Event, text: str,
                 kb: Optional[InlineKeyboardMarkup] = None,
                 fresh: bool = False) -> None:
    """
    Показать экран в панели.

    event: Message (пользователь что-то написал) или CallbackQuery (нажал кнопку).
    fresh=True: удалить старую панель и отправить новую внизу чата (для /start и /menu).
    """
    if isinstance(event, CallbackQuery):
        msg = event.message
        chat_id = msg.chat.id
        bot = msg.bot
        panel_id = msg.message_id  # нажали кнопку на этом сообщении, оно и есть панель
        user_msg_id = None
    else:
        chat_id = event.chat.id
        bot = event.bot
        panel_id = _panels.get(chat_id)
        user_msg_id = event.message_id

    # убираем сообщение пользователя (команду, фамилию, дату, файл)
    if user_msg_id is not None:
        await _safe_delete(bot, chat_id, user_msg_id)

    if panel_id and not fresh:
        if await _try_edit(bot, chat_id, panel_id, text, kb):
            _panels[chat_id] = panel_id
            return

    # редактировать нечего (первое сообщение, панель удалена, или fresh): шлём новую
    if panel_id:
        await _safe_delete(bot, chat_id, panel_id)
    sent = await bot.send_message(chat_id, text, reply_markup=kb)
    _panels[chat_id] = sent.message_id
