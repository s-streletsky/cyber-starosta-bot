"""Safe user notifications: a delivery failure must never break the handler flow."""

import logging
from typing import Any

from handlers.log_helpers import user_tag
from storage import Storage

logger = logging.getLogger(__name__)


async def notify_safe(
    bot: Any,
    storage: Storage,
    user_id: int,
    text: str,
    *,
    reply_markup: Any = None,
    context: str = "",
) -> None:
    """Send a message; log a warning with the id (@username) tag on failure."""
    try:
        await bot.send_message(user_id, text, reply_markup=reply_markup)
    except Exception:
        suffix = f" ({context})" if context else ""
        logger.warning(
            "Failed to notify %s%s",
            await user_tag(bot, storage, user_id),
            suffix,
            exc_info=True,
        )
