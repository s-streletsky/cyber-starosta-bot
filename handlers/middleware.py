"""ACL by role/status: catalog-open commands, onboarding, then admitted members."""

import logging
from typing import Any, Awaitable, Callable, Dict

from aiogram import BaseMiddleware
from aiogram.types import Update

import texts
from handlers.log_helpers import user_tag
from handlers.start import is_onboarding_state
from services.help import OPEN_COMMANDS
from services.members import is_admin, is_approved

logger = logging.getLogger(__name__)


def is_open_command(text: str | None) -> bool:
    """True for an open /command (from the catalog), including /command@bot."""
    if not text:
        return False
    stripped = text.strip()
    if not stripped:
        return False
    command = stripped.split(maxsplit=1)[0].split("@", 1)[0]
    # Exactly one leading slash, matching the aiogram Command filter semantics.
    return command.startswith("/") and command[1:] in OPEN_COMMANDS


async def _allow(
    handler: Callable[[Update, Dict[str, Any]], Awaitable[Any]],
    event: Update,
    data: Dict[str, Any],
    bot: Any,
    storage: Any,
    user_id: int,
    user: Any,
    message: str,
) -> Any:
    logger.debug(message, await user_tag(bot, storage, user_id, user))
    return await handler(event, data)


class AccessControlMiddleware(BaseMiddleware):
    async def __call__(
        self,
        handler: Callable[[Update, Dict[str, Any]], Awaitable[Any]],
        event: Update,
        data: Dict[str, Any],
    ) -> Any:
        inner_event = event.message or event.callback_query
        if not inner_event or not inner_event.from_user:
            return await handler(event, data)

        user = inner_event.from_user
        user_id = user.id
        storage = data.get("storage")
        bot = data.get("bot")

        # The only messages open to everyone: the commands the /help catalog marks
        # AUDIENCE_ALL (an intentional ACL exception; every other command requires
        # admission).
        if event.message and is_open_command(event.message.text):
            return await _allow(
                handler, event, data, bot, storage, user_id, user,
                "Allow open command for user %s",
            )

        # Onboarding full-name text: request not approved yet, but the name must be allowed.
        if is_onboarding_state(data.get("raw_state")):
            return await _allow(
                handler, event, data, bot, storage, user_id, user,
                "Allow onboarding text for user %s",
            )

        if await _is_admitted(storage, user_id):
            return await _allow(
                handler, event, data, bot, storage, user_id, user,
                "Access allowed for user %s",
            )

        logger.info(
            "Access denied for user %s",
            await user_tag(bot, storage, user_id, user),
        )
        if event.callback_query:
            await event.callback_query.answer(texts.ACCESS_DENIED, show_alert=True)
        elif event.message:
            await event.message.answer(texts.ACCESS_DENIED)
        return None


async def _is_admitted(storage: Any, user_id: int) -> bool:
    """Env admin is always admitted; others by the approved status in the roster."""
    if is_admin(user_id):
        return True
    if storage is None:
        return False
    member = await storage.get_member(user_id)
    return is_approved(member)
