"""Tests for the user_tag logging helper: source priority and tag format."""

from aiogram.types import User

from handlers.log_helpers import user_tag
from storage import Storage


def _user(username: str | None) -> User:
    return User(id=111, is_bot=False, first_name="Іван", username=username)


async def test_user_tag_uses_from_user_username():
    tag = await user_tag(bot=None, storage=None, user_id=111, user=_user("@ivan"))

    assert tag == "id=111 (@ivan)"


async def test_user_tag_adds_missing_at_prefix():
    tag = await user_tag(bot=None, storage=None, user_id=111, user=_user("ivan"))

    assert tag == "id=111 (@ivan)"


async def test_user_tag_does_not_read_storage_when_user_has_username():
    class ForbiddenStorage:
        async def get_member(self, user_id: int):
            raise AssertionError("members.json must not be read when username is in the update")

    tag = await user_tag(
        bot=None, storage=ForbiddenStorage(), user_id=111, user=_user("ivan")
    )

    assert tag == "id=111 (@ivan)"


async def test_user_tag_falls_back_to_storage(tmp_path):
    storage = Storage(tmp_path)
    await storage.upsert_member(111, "Петренко Іван", "ivan")

    tag = await user_tag(bot=None, storage=storage, user_id=111, user=_user(None))

    assert tag == "id=111 (@ivan)"


async def test_user_tag_unknown_username():
    tag = await user_tag(bot=None, storage=None, user_id=111, user=_user(None))

    assert tag == "id=111 (username unknown)"
