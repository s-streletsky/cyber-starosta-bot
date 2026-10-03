"""Unit tests for handlers/admin.py: promote, demote, remove, sethead."""

from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

import texts
from handlers.admin import cmd_demote, cmd_promote, cmd_sethead, handle_admin_callback
from storage import MEMBER_APPROVED, MEMBER_REMOVED, Storage
from tests.fakes import ADMIN_ID, _FakeCallback, _FakeMessage, _inline_button_texts


def _first_answer_text(fake) -> str:
    return fake.answers[0][0] if fake.answers else ""


def _first_edit_text(fake) -> str:
    return fake.edits[0][0] if fake.edits else ""


# --- cmd_promote ---


@pytest.mark.asyncio
async def test_cmd_promote_non_admin_denied(tmp_path):
    storage = Storage(tmp_path)
    msg = _FakeMessage(from_user_id=111)
    await cmd_promote(msg, storage)

    assert any(texts.ADMIN_ONLY == t for t, _ in msg.answers)


@pytest.mark.asyncio
async def test_cmd_promote_admin_with_candidates(tmp_path):
    storage = Storage(tmp_path)
    await storage.upsert_member(222, "Студент Тестовий", "student", status=MEMBER_APPROVED)

    msg = _FakeMessage(from_user_id=ADMIN_ID)
    await cmd_promote(msg, storage)

    assert len(msg.answers) == 1
    text, markup = msg.answers[0]
    assert text == texts.PROMOTE_PROMPT
    assert len(_inline_button_texts(markup)) == 1


@pytest.mark.asyncio
async def test_cmd_promote_no_candidates(tmp_path):
    storage = Storage(tmp_path)
    msg = _FakeMessage(from_user_id=ADMIN_ID)
    await cmd_promote(msg, storage)

    assert any(texts.PROMOTE_EMPTY == t for t, _ in msg.answers)


# --- pick_promote + set_role ---


@pytest.mark.asyncio
async def test_pick_promote_shows_role_choice(tmp_path):
    storage = Storage(tmp_path)
    await storage.upsert_member(222, "Студент Тестовий", "student", status=MEMBER_APPROVED)

    callback = _FakeCallback(ADMIN_ID)
    callback_data = SimpleNamespace(action="pick_promote", user_id=222, role=None)
    await handle_admin_callback(callback, storage, callback_data)

    assert len(callback.message.edits) == 1
    text, markup = callback.message.edits[0]
    assert text.startswith("Обери роль для ")
    assert texts.BUTTON_ROLE_GROUP_LEAD in _inline_button_texts(markup)
    assert texts.BUTTON_ROLE_SUPERVISOR in _inline_button_texts(markup)


@pytest.mark.asyncio
async def test_set_role_promotes_and_notifies(tmp_path):
    storage = Storage(tmp_path)
    await storage.upsert_member(222, "Студент Тестовий", "student", status=MEMBER_APPROVED)

    bot = AsyncMock()
    callback = _FakeCallback(ADMIN_ID, bot=bot)
    callback_data = SimpleNamespace(action="set_role", user_id=222, role="group_lead")
    await handle_admin_callback(callback, storage, callback_data)

    member = await storage.get_member(222)
    assert "group_lead" in member["roles"]

    bot.send_message.assert_called_once()

    assert _first_edit_text(callback.message).startswith("✅ ")


@pytest.mark.asyncio
async def test_set_role_invalid_role_is_stale(tmp_path):
    storage = Storage(tmp_path)
    await storage.upsert_member(222, "Студент Тестовий", "student", status=MEMBER_APPROVED)

    callback = _FakeCallback(ADMIN_ID)
    callback_data = SimpleNamespace(action="set_role", user_id=222, role="bogus")
    await handle_admin_callback(callback, storage, callback_data)

    assert any(texts.STALE_CARD == args[0] for args, _ in callback.answers if args)
    member = await storage.get_member(222)
    assert member["roles"] == []


@pytest.mark.asyncio
async def test_pick_promote_stale_when_member_has_role(tmp_path):
    storage = Storage(tmp_path)
    await storage.upsert_member(222, "Студент Тестовий", "student", status=MEMBER_APPROVED)
    await storage.add_role(222, "group_lead")

    callback = _FakeCallback(ADMIN_ID)
    callback_data = SimpleNamespace(action="pick_promote", user_id=222, role=None)
    await handle_admin_callback(callback, storage, callback_data)

    assert len(callback.message.edits) == 0
    assert any(texts.STALE_CARD == args[0] for args, _ in callback.answers if args)


# --- demote ---


@pytest.mark.asyncio
async def test_demote_removes_role(tmp_path):
    storage = Storage(tmp_path)
    await storage.upsert_member(222, "Студент Тестовий", "student", status=MEMBER_APPROVED)
    await storage.add_role(222, "group_lead")

    bot = AsyncMock()
    callback = _FakeCallback(ADMIN_ID, bot=bot)
    callback_data = SimpleNamespace(action="demote", user_id=222, role=None)
    await handle_admin_callback(callback, storage, callback_data)

    member = await storage.get_member(222)
    assert member["roles"] == []
    assert _first_edit_text(callback.message).startswith(texts.DEMOTE_DONE.split("{")[0])


@pytest.mark.asyncio
async def test_demote_head_lead_clears_head_lead_flag(tmp_path):
    storage = Storage(tmp_path)
    await storage.upsert_member(222, "Студент Тестовий", "student", status=MEMBER_APPROVED)
    await storage.add_role(222, "group_lead")
    await storage.set_head_lead(222)

    bot = AsyncMock()
    callback = _FakeCallback(ADMIN_ID, bot=bot)
    callback_data = SimpleNamespace(action="demote", user_id=222, role=None)
    await handle_admin_callback(callback, storage, callback_data)

    assert await storage.get_head_lead() is None
    assert texts.HEAD_LEAD_CLEARED in _first_edit_text(callback.message)


@pytest.mark.asyncio
async def test_demote_no_candidates(tmp_path):
    storage = Storage(tmp_path)
    msg = _FakeMessage(from_user_id=ADMIN_ID)
    await cmd_demote(msg, storage)

    assert any(texts.DEMOTE_EMPTY == t for t, _ in msg.answers)


# --- remove ---


@pytest.mark.asyncio
async def test_remove_sets_removed_and_notifies(tmp_path):
    storage = Storage(tmp_path)
    await storage.upsert_member(222, "Студент Тестовий", "student", status=MEMBER_APPROVED)

    bot = AsyncMock()
    callback = _FakeCallback(ADMIN_ID, bot=bot)
    callback_data = SimpleNamespace(action="remove", user_id=222, role=None)
    await handle_admin_callback(callback, storage, callback_data)

    member = await storage.get_member(222)
    assert member["status"] == MEMBER_REMOVED

    bot.send_message.assert_called_once()
    assert bot.send_message.call_args[0][1] == texts.ACCESS_CLOSED_NOTIFY


@pytest.mark.asyncio
async def test_remove_non_admin_denied(tmp_path):
    storage = Storage(tmp_path)
    await storage.upsert_member(222, "Студент Тестовий", "student", status=MEMBER_APPROVED)

    callback = _FakeCallback(111)
    callback_data = SimpleNamespace(action="remove", user_id=222, role=None)
    await handle_admin_callback(callback, storage, callback_data)

    assert any(texts.ACCESS_DENIED == args[0] for args, _ in callback.answers if args)

    member = await storage.get_member(222)
    assert member["status"] == MEMBER_APPROVED


# --- sethead ---


@pytest.mark.asyncio
async def test_sethead_sets_head_lead(tmp_path):
    storage = Storage(tmp_path)
    await storage.upsert_member(222, "Студент Тестовий", "student", status=MEMBER_APPROVED)
    await storage.add_role(222, "group_lead")

    callback = _FakeCallback(ADMIN_ID)
    callback_data = SimpleNamespace(action="sethead", user_id=222, role=None)
    await handle_admin_callback(callback, storage, callback_data)

    assert await storage.get_head_lead() == 222
    assert _first_edit_text(callback.message).startswith(texts.HEAD_LEAD_SET.split("{")[0])


@pytest.mark.asyncio
async def test_sethead_toggle_clears(tmp_path):
    storage = Storage(tmp_path)
    await storage.upsert_member(222, "Студент Тестовий", "student", status=MEMBER_APPROVED)
    await storage.add_role(222, "group_lead")
    await storage.set_head_lead(222)

    callback = _FakeCallback(ADMIN_ID)
    callback_data = SimpleNamespace(action="sethead", user_id=222, role=None)
    await handle_admin_callback(callback, storage, callback_data)

    assert await storage.get_head_lead() is None
    assert texts.HEAD_LEAD_CLEARED == _first_edit_text(callback.message)


@pytest.mark.asyncio
async def test_sethead_stale_when_not_group_lead(tmp_path):
    storage = Storage(tmp_path)
    await storage.upsert_member(222, "Студент Тестовий", "student", status=MEMBER_APPROVED)

    callback = _FakeCallback(ADMIN_ID)
    callback_data = SimpleNamespace(action="sethead", user_id=222, role=None)
    await handle_admin_callback(callback, storage, callback_data)

    assert any(texts.STALE_CARD == args[0] for args, _ in callback.answers if args)


@pytest.mark.asyncio
async def test_sethead_no_candidates(tmp_path):
    storage = Storage(tmp_path)
    msg = _FakeMessage(from_user_id=ADMIN_ID)
    await cmd_sethead(msg, storage)

    assert any(texts.HEAD_LEAD_EMPTY == t for t, _ in msg.answers)
