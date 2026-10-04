"""/help: reply with the slash commands available to the caller's role."""

from aiogram import Router
from aiogram.filters import Command
from aiogram.types import Message

from services.help import build_help_text
from services.members import is_admin
from storage import Storage

router = Router()


@router.message(Command("help"))
async def cmd_help(message: Message, storage: Storage) -> None:
    """Reply with the role-filtered command list."""
    user = message.from_user
    if not user:
        return

    member = await storage.get_member(user.id)
    text = build_help_text(member, is_admin(user.id))
    await message.answer(text)
