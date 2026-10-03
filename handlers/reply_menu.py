"""Role-aware reply keyboard for paths that have no FSM step (errors, cancels).

Reading the roster is best-effort: a storage failure must never break the
error/cancel path, so it falls back to the student keyboard.
"""

import logging

from aiogram.types import ReplyKeyboardMarkup

from keyboards.menu import role_keyboard
from services.members import synthetic_member

logger = logging.getLogger(__name__)


async def menu_for(storage, user_id: int, is_admin: bool) -> ReplyKeyboardMarkup:
    """Builds the reply keyboard for a user's current roles (best-effort)."""
    try:
        member = await storage.get_member(user_id)
    except Exception:
        logger.warning("menu_for: failed to read the roster for id=%s", user_id, exc_info=True)
        member = synthetic_member([])
    return role_keyboard(member, is_admin=is_admin)
