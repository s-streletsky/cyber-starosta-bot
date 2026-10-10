"""Tests for handlers/reply_menu.py: best-effort role keyboard lookup."""

import texts
from handlers.reply_menu import menu_for
from services.members import ROLE_GROUP_LEAD
from storage import MEMBER_APPROVED, Storage


class _BrokenStorage:
    async def get_member(self, user_id: int) -> dict:
        raise RuntimeError("roster read failed")


def _button_texts(markup) -> list[str]:
    return [button.text for row in markup.keyboard for button in row]


async def test_menu_for_falls_back_to_student_keyboard_on_read_failure():
    markup = await menu_for(_BrokenStorage(), 111, is_admin=False)

    assert _button_texts(markup) == [texts.MENU_ABSENCE, texts.MENU_DELETE]


async def test_menu_for_returns_role_keyboard_on_success(tmp_path):
    storage = Storage(tmp_path)
    await storage.upsert_member(111, "Лід Групи", "lead", status=MEMBER_APPROVED)
    await storage.add_role(111, ROLE_GROUP_LEAD)

    markup = await menu_for(storage, 111, is_admin=False)

    assert _button_texts(markup) == [
        texts.MENU_ABSENCE,
        texts.MENU_DELETE,
        texts.MENU_REPORTS,
        texts.MENU_BROADCAST,
    ]
