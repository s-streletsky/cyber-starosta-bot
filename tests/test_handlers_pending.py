"""Unit tests for handlers/pending.py: /pending, request cards, approve/reject."""

from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

import texts
from handlers.pending import cmd_pending, handle_request, send_request_card
from storage import MEMBER_APPROVED, MEMBER_PENDING, Storage
from tests.fakes import ADMIN_ID, _FakeCallback, _FakeMessage, _inline_button_texts

# --- cmd_pending ---


@pytest.mark.asyncio
async def test_cmd_pending_non_manager_denied(tmp_path):
    storage = Storage(tmp_path)
    msg = _FakeMessage(from_user_id=111)
    await cmd_pending(msg, storage)

    assert any(texts.NOT_A_MANAGER == t for t, _ in msg.answers)


@pytest.mark.asyncio
async def test_cmd_pending_manager_empty(tmp_path):
    storage = Storage(tmp_path)
    msg = _FakeMessage(from_user_id=ADMIN_ID)
    await cmd_pending(msg, storage)

    assert any(texts.PENDING_EMPTY == t for t, _ in msg.answers)


@pytest.mark.asyncio
async def test_cmd_pending_with_pending(tmp_path):
    storage = Storage(tmp_path)
    await storage.upsert_member(222, "Студент Тестовий", "student", status=MEMBER_PENDING)

    msg = _FakeMessage(from_user_id=ADMIN_ID)
    await cmd_pending(msg, storage)

    assert len(msg.answers) == 1
    text, markup = msg.answers[0]
    assert "Заявка:" in text
    assert texts.BUTTON_ACCEPT in _inline_button_texts(markup)
    assert texts.BUTTON_REJECT in _inline_button_texts(markup)


# --- handle_request: accept ---


@pytest.mark.asyncio
async def test_handle_request_accept(tmp_path):
    storage = Storage(tmp_path)
    await storage.upsert_member(222, "Студент Тестовий", "student", status=MEMBER_PENDING)

    bot = AsyncMock()
    callback = _FakeCallback(ADMIN_ID, bot=bot)
    callback_data = SimpleNamespace(action="accept", user_id=222)
    await handle_request(callback, storage, callback_data)

    member = await storage.get_member(222)
    assert member["status"] == MEMBER_APPROVED

    bot.send_message.assert_called_once()

    assert callback.message.edits[0][0].startswith(texts.CARD_APPROVED.split("{")[0])


@pytest.mark.asyncio
async def test_approval_notification_has_role_keyboard(tmp_path):
    storage = Storage(tmp_path)
    await storage.upsert_member(222, "Студент Тестовий", "student", status=MEMBER_PENDING)

    bot = AsyncMock()
    callback = _FakeCallback(ADMIN_ID, bot=bot)
    callback_data = SimpleNamespace(action="accept", user_id=222)
    await handle_request(callback, storage, callback_data)

    bot.send_message.assert_called_once()
    markup = bot.send_message.call_args[1]["reply_markup"]
    buttons = [button.text for row in markup.keyboard for button in row]
    assert texts.MENU_ABSENCE in buttons  # approved student gets the absence button


# --- handle_request: reject ---


@pytest.mark.asyncio
async def test_handle_request_reject(tmp_path):
    storage = Storage(tmp_path)
    await storage.upsert_member(222, "Студент Тестовий", "student", status=MEMBER_PENDING)

    bot = AsyncMock()
    callback = _FakeCallback(ADMIN_ID, bot=bot)
    callback_data = SimpleNamespace(action="reject", user_id=222)
    await handle_request(callback, storage, callback_data)

    member = await storage.get_member(222)
    assert member is None

    assert callback.message.edits[0][0].startswith(texts.CARD_REJECTED.split("{")[0])


# --- stale callback ---


@pytest.mark.asyncio
async def test_handle_request_stale_not_pending(tmp_path):
    storage = Storage(tmp_path)
    await storage.upsert_member(222, "Студент Тестовий", "student", status=MEMBER_APPROVED)

    callback = _FakeCallback(ADMIN_ID)
    callback_data = SimpleNamespace(action="accept", user_id=222)
    await handle_request(callback, storage, callback_data)

    assert any(texts.STALE_CARD == args[0] for args, _ in callback.answers if args)


# --- approve/reject race: exactly one manager wins ---

LEAD_ID = 888888888


@pytest.mark.asyncio
async def test_two_managers_sequential_has_exactly_one_winner(tmp_path):
    storage = Storage(tmp_path)
    await storage.upsert_member(222, "Студент Тестовий", "student", status=MEMBER_PENDING)
    # Create a lead (manager) so we have two managers
    await storage.upsert_member(LEAD_ID, "Лід Групи", "lead", status=MEMBER_APPROVED)
    await storage.add_role(LEAD_ID, "group_lead")

    admin_callback = _FakeCallback(ADMIN_ID)
    admin_data = SimpleNamespace(action="accept", user_id=222)
    lead_callback = _FakeCallback(LEAD_ID)
    lead_data = SimpleNamespace(action="accept", user_id=222)

    await handle_request(admin_callback, storage, admin_data)
    await handle_request(lead_callback, storage, lead_data)

    # Success verdict goes to message.edit; stale goes to callback.answer
    admin_edits = [t for t, _ in admin_callback.message.edits]
    lead_edits = [t for t, _ in lead_callback.message.edits]
    admin_answers = [args[0] for args, _ in admin_callback.answers if args]
    lead_answers = [args[0] for args, _ in lead_callback.answers if args]

    admin_ok = any(t.startswith(texts.CARD_APPROVED.split("{")[0]) for t in admin_edits)
    lead_ok = any(t.startswith(texts.CARD_APPROVED.split("{")[0]) for t in lead_edits)
    admin_stale = texts.STALE_CARD in admin_answers
    lead_stale = texts.STALE_CARD in lead_answers

    assert admin_ok ^ lead_ok  # exactly one succeeded
    assert admin_stale ^ lead_stale  # exactly one got stale
    assert (admin_ok and lead_stale) or (lead_ok and admin_stale)

    member = await storage.get_member(222)
    assert member is not None and member["status"] == MEMBER_APPROVED


@pytest.mark.asyncio
async def test_approve_non_pending_is_stale(tmp_path):
    storage = Storage(tmp_path)
    await storage.upsert_member(222, "Студент Тестовий", "student", status=MEMBER_APPROVED)

    callback = _FakeCallback(ADMIN_ID)
    callback_data = SimpleNamespace(action="accept", user_id=222)
    await handle_request(callback, storage, callback_data)

    assert any(texts.STALE_CARD == args[0] for args, _ in callback.answers if args)
    member = await storage.get_member(222)
    assert member is not None and member["status"] == MEMBER_APPROVED


# --- send_request_card delivery ---


@pytest.mark.asyncio
async def test_send_request_card_to_active_lead(tmp_path):
    storage = Storage(tmp_path)
    await storage.upsert_member(333, "Лід Групи", "lead", status=MEMBER_APPROVED)
    await storage.add_role(333, "group_lead")
    await storage.set_head_lead(333)

    bot = AsyncMock()
    member = {"display_name": "Новий Студент", "username": "newbie"}
    await send_request_card(bot, storage, 222, member)

    bot.send_message.assert_called_once()
    assert bot.send_message.call_args[0][0] == 333


@pytest.mark.asyncio
async def test_send_request_card_fallback_to_admins(tmp_path):
    storage = Storage(tmp_path)
    await storage.upsert_member(333, "Лід Групи", "lead", status=MEMBER_APPROVED)
    await storage.add_role(333, "group_lead")
    await storage.set_head_lead(333)
    # Lead removed — no active group_lead as lead
    await storage.remove_member(333)

    bot = AsyncMock()
    member = {"display_name": "Новий Студент", "username": "newbie"}
    await send_request_card(bot, storage, 222, member)

    bot.send_message.assert_called_once()
    assert bot.send_message.call_args[0][0] == ADMIN_ID


@pytest.mark.asyncio
async def test_send_request_card_no_recipients(tmp_path, monkeypatch):
    monkeypatch.setattr("handlers.pending.ADMIN_USER_IDS", [])
    storage = Storage(tmp_path)

    bot = AsyncMock()
    bot.get_chat = AsyncMock(return_value=SimpleNamespace(username=None))
    member = {"display_name": "Новий Студент", "username": "newbie"}
    await send_request_card(bot, storage, 222, member)

    bot.send_message.assert_not_called()
