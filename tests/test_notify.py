"""Tests for handlers/notify.py: delivery failures never propagate."""

import logging
from unittest.mock import AsyncMock

from handlers.notify import notify_safe
from storage import Storage


async def test_notify_safe_sends_message(tmp_path):
    storage = Storage(tmp_path)
    bot = AsyncMock()

    await notify_safe(bot, storage, 111, "hello", context="test")

    bot.send_message.assert_called_once()
    assert bot.send_message.call_args[0][0] == 111
    assert bot.send_message.call_args[0][1] == "hello"


async def test_notify_safe_swallows_send_failure(tmp_path, caplog):
    storage = Storage(tmp_path)
    bot = AsyncMock()
    bot.send_message = AsyncMock(side_effect=RuntimeError("boom"))
    bot.get_chat = AsyncMock(side_effect=RuntimeError("no chat"))

    with caplog.at_level(logging.WARNING, logger="handlers.notify"):
        await notify_safe(bot, storage, 111, "hello")

    assert any(record.levelno == logging.WARNING for record in caplog.records)
