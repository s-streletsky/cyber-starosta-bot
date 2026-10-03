"""Shared test fakes for handler tests.

Kept identical across test files so handlers are exercised against the same
in-memory stand-ins for aiogram types.
"""

from types import SimpleNamespace
from typing import Any
from unittest.mock import AsyncMock

ADMIN_ID = 999999999


def make_update(message=None, callback_query=None):
    return SimpleNamespace(message=message, callback_query=callback_query)


class _FakeMessage:
    def __init__(
        self,
        from_user_id: int | None = None,
        text: str | None = None,
    ) -> None:
        if from_user_id:
            self.from_user = SimpleNamespace(
                id=from_user_id, full_name="Тестовий Студент", username="testuser"
            )
        else:
            self.from_user = None
        self.bot = None
        self.text = text
        self.answers: list[tuple[str, object]] = []
        self.edits: list[tuple[str, object]] = []

    async def answer(self, text: str, reply_markup=None) -> None:
        self.answers.append((text, reply_markup))

    async def edit_text(self, text: str, reply_markup=None) -> None:
        self.edits.append((text, reply_markup))


class _FakeCallback:
    def __init__(self, user_id: int, bot=None) -> None:
        self.from_user = SimpleNamespace(id=user_id)
        self.message = _FakeMessage()
        self.bot = bot or AsyncMock()
        self.answers: list = []

    async def answer(self, *args, **kwargs):
        self.answers.append((args, kwargs))


class _FakeState:
    def __init__(self, data: dict | None = None) -> None:
        self._data: dict[str, Any] = dict(data) if data else {}
        self.cleared = False
        self.set_to: object | None = None

    async def get_data(self) -> dict[str, Any]:
        return dict(self._data)

    async def update_data(self, **kwargs: Any) -> None:
        self._data.update(kwargs)

    async def set_state(self, state: object) -> None:
        self.set_to = state

    async def set_data(self, data: dict[str, Any]) -> None:
        self._data = dict(data)

    async def clear(self) -> None:
        self._data = {}
        self.cleared = True


def _reply_button_texts(markup) -> list[str]:
    """Button labels from a reply keyboard markup."""
    return [button.text for row in markup.keyboard for button in row]


def _inline_button_texts(markup) -> list[str]:
    """Button labels from an inline keyboard markup."""
    return [button.text for row in markup.inline_keyboard for button in row]
