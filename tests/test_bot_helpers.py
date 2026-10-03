"""Tests for bot.py helpers: FSM key, update author, inactive-head-lead warning."""

import logging
from types import SimpleNamespace

from aiogram.fsm.storage.base import StorageKey

from bot import _fsm_key, _update_user, _warn_if_head_lead_inactive
from services.members import ROLE_GROUP_LEAD
from storage import MEMBER_APPROVED, Storage
from tests.fakes import make_update as _update


def test_fsm_key_from_message():
    update = _update(
        message=SimpleNamespace(from_user=SimpleNamespace(id=111), chat=SimpleNamespace(id=222))
    )

    assert _fsm_key(update, bot_id=42) == StorageKey(bot_id=42, chat_id=222, user_id=111)


def test_fsm_key_message_without_user_is_none():
    update = _update(message=SimpleNamespace(from_user=None, chat=SimpleNamespace(id=222)))

    assert _fsm_key(update, bot_id=42) is None


def test_fsm_key_from_callback_with_message():
    callback_query = SimpleNamespace(
        from_user=SimpleNamespace(id=111),
        message=SimpleNamespace(chat=SimpleNamespace(id=222)),
    )
    update = _update(callback_query=callback_query)

    assert _fsm_key(update, bot_id=42) == StorageKey(bot_id=42, chat_id=222, user_id=111)


def test_fsm_key_from_callback_without_message():
    callback_query = SimpleNamespace(from_user=SimpleNamespace(id=111), message=None)
    update = _update(callback_query=callback_query)

    assert _fsm_key(update, bot_id=42) == StorageKey(bot_id=42, chat_id=111, user_id=111)


def test_fsm_key_without_message_and_callback_is_none():
    assert _fsm_key(_update(), bot_id=42) is None


def test_update_user_from_message():
    user = SimpleNamespace(id=111)
    update = _update(message=SimpleNamespace(from_user=user))

    assert _update_user(update) is user


def test_update_user_from_callback():
    user = SimpleNamespace(id=111)
    update = _update(callback_query=SimpleNamespace(from_user=user))

    assert _update_user(update) is user


def test_update_user_without_event_is_none():
    assert _update_user(_update()) is None


async def test_warn_if_head_lead_inactive_is_quiet_for_active_lead(tmp_path, caplog):
    storage = Storage(tmp_path)
    await storage.upsert_member(111, "Лід Групи", "lead", status=MEMBER_APPROVED)
    await storage.add_role(111, ROLE_GROUP_LEAD)
    await storage.set_head_lead(111)

    with caplog.at_level(logging.WARNING, logger="bot"):
        await _warn_if_head_lead_inactive(storage)

    assert not caplog.records


async def test_warn_if_head_lead_inactive_warns_for_non_group_lead(tmp_path, caplog):
    storage = Storage(tmp_path)
    await storage.upsert_member(111, "Студент Тестовий", "student", status=MEMBER_APPROVED)
    await storage.set_head_lead(111)

    with caplog.at_level(logging.WARNING, logger="bot"):
        await _warn_if_head_lead_inactive(storage)

    assert any(record.levelno == logging.WARNING for record in caplog.records)
