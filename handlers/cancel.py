"""/cancel: interrupt any active FSM flow and return to the role reply menu."""

from aiogram import Router
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.types import Message

import texts
from handlers.reply_menu import menu_for
from services.members import is_admin as is_env_admin
from storage import Storage

router = Router()


@router.message(Command("cancel"))
async def cancel_any(message: Message, state: FSMContext, storage: Storage) -> None:
    """Cancel the current flow (if any) and show the role menu."""
    user = message.from_user
    if user is None:
        return
    raw = await state.get_state()
    await state.clear()
    reply = texts.CANCELLED if raw is not None else texts.NOTHING_TO_CANCEL
    await message.answer(
        reply, reply_markup=await menu_for(storage, user.id, is_env_admin(user.id))
    )
