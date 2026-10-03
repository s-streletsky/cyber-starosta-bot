"""Logging helpers: user tag «id=... (@username)» for logs.

The full name (display_name) never goes into logs — only Telegram ID and @username.
"""

import logging

from aiogram import Bot
from aiogram.types import User

from storage import Storage

logger = logging.getLogger(__name__)


def _normalize_username(username: str | None) -> str | None:
    """Normalizes username to @nick; an empty value → None."""
    if not username:
        return None
    username = username.strip()
    if not username:
        return None
    if not username.startswith("@"):
        username = f"@{username}"
    return username


def _format_tag(user_id: int, username: str | None) -> str:
    """Tag format: id=111 (@ivan) or id=111 (username unknown)."""
    normalized = _normalize_username(username)
    if normalized is None:
        return f"id={user_id} (username unknown)"
    return f"id={user_id} ({normalized})"


async def user_tag(
    bot: Bot | None,
    storage: Storage | None,
    user_id: int,
    user: User | None = None,
) -> str:
    """User tag for logs: Telegram ID + @username.

    Username sources by priority:
    1. user.username from the update's from_user (cheap, no disk read);
    2. storage.get_member(user_id)["username"];
    3. bot.get_chat(user_id).username (Telegram API — only if the first two are unavailable).

    The helper never crashes: storage/get_chat exceptions are caught and logged.
    """
    username: str | None = None

    if user is not None:
        username = getattr(user, "username", None) or None

    if username is None and storage is not None:
        try:
            member = await storage.get_member(user_id)
        except Exception:
            logger.warning(
                "user_tag: failed to read the roster for %s",
                _format_tag(user_id, None),
                exc_info=True,
            )
            member = None
        if member is not None:
            username = member.get("username") or None

    if username is None and bot is not None:
        try:
            chat = await bot.get_chat(user_id)
        except Exception:
            logger.warning(
                "user_tag: bot.get_chat failed for %s",
                _format_tag(user_id, None),
                exc_info=True,
            )
            chat = None
        if chat is not None:
            username = getattr(chat, "username", None) or None

    return _format_tag(user_id, username)
