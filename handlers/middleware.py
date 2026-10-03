"""ACL by roles and statuses: /start and onboarding are open to all, the rest — approved."""

import logging
from typing import Any, Awaitable, Callable, Dict

from aiogram import BaseMiddleware
from aiogram.types import Update

import texts
from handlers.log_helpers import user_tag
from handlers.start import is_onboarding_state
from services.members import is_admin, is_approved

logger = logging.getLogger(__name__)


def is_start_command(text: str | None) -> bool:
    """True for messages starting with /start (including /start@my_bot)."""
    if not text:
        return False
    first_word = text.strip().split(maxsplit=1)[0]
    return first_word.split("@", 1)[0] == "/start"


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

        # The only message open to everyone: /start.
        if event.message and is_start_command(event.message.text):
            return await _allow(
                handler, event, data, bot, storage, user_id, user,
                "Allow /start for user %s",
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
