"""Unit tests for the logical-deletion handlers in handlers/absence.py."""

from datetime import date

import pytest

import texts
from callbacks import DayCb
from config import TZ
from handlers.absence import (
    AbsenceForm,
    confirm_delete,
    delete_back,
    delete_next_to_confirm,
    start_delete,
    toggle_delete_day,
)
from services.absence import build_days
from storage import MEMBER_APPROVED, Storage
from tests.fakes import _FakeCallback, _FakeMessage, _FakeState

TODAY = date(2026, 10, 3)
FIXED_DAYS = build_days(TZ, today=TODAY)


def _fix_window(monkeypatch) -> None:
    monkeypatch.setattr("handlers.absence.build_days", lambda tz: FIXED_DAYS)
    monkeypatch.setattr("handlers.absence.current_day", lambda: TODAY)


# --- start_delete ---


async def test_start_delete_denied_for_non_approved(tmp_path):
    storage = Storage(tmp_path)
    msg = _FakeMessage(from_user_id=111)
    state = _FakeState()

    await start_delete(msg, state, storage)

    assert any(texts.NOT_ALLOWED_ABSENCE == text for text, _ in msg.answers)
    assert state.set_to is None


async def test_start_delete_denied_for_supervisor(tmp_path):
    storage = Storage(tmp_path)
    await storage.upsert_member(111, "Супервайзер Тест", "sup", status=MEMBER_APPROVED)
    await storage.add_role(111, "supervisor")
    msg = _FakeMessage(from_user_id=111)
    state = _FakeState()

    await start_delete(msg, state, storage)

    assert any(texts.NOT_ALLOWED_ABSENCE == text for text, _ in msg.answers)
    assert state.set_to is None


async def test_start_delete_without_records_shows_nothing(tmp_path, monkeypatch):
    _fix_window(monkeypatch)
    storage = Storage(tmp_path)
    await storage.upsert_member(111, "Студент Тестовий", "student", status=MEMBER_APPROVED)
    msg = _FakeMessage(from_user_id=111)
    state = _FakeState()

    await start_delete(msg, state, storage)

    assert state.cleared
    assert any(text == texts.DELETE_NOTHING for text, _ in msg.answers)


async def test_start_delete_lists_only_existing_records(tmp_path, monkeypatch):
    _fix_window(monkeypatch)
    storage = Storage(tmp_path)
    await storage.upsert_member(111, "Студент Тестовий", "student", status=MEMBER_APPROVED)
    await storage.upsert_absences_batch(111, ["2026-10-03"], "illness", None)
    msg = _FakeMessage(from_user_id=111)
    state = _FakeState()

    await start_delete(msg, state, storage)

    assert state.set_to == AbsenceForm.delete_day
    text, markup = msg.answers[0]
    assert text == texts.DELETE_PROMPT.format(count=0)
    day_buttons = [
        button
        for row in markup.inline_keyboard
        for button in row
        if button.callback_data.startswith("d:")
    ]
    assert len(day_buttons) == 1
    assert day_buttons[0].callback_data == "d:2026-10-03"


# --- delete picker ---


async def test_toggle_delete_day_selects_record(tmp_path, monkeypatch):
    _fix_window(monkeypatch)
    storage = Storage(tmp_path)
    await storage.upsert_member(111, "Студент Тестовий", "student", status=MEMBER_APPROVED)
    await storage.upsert_absences_batch(111, ["2026-10-03"], "illness", None)
    callback = _FakeCallback(111)
    state = _FakeState()

    await toggle_delete_day(callback, state, storage, DayCb(date="2026-10-03"))

    assert await state.get_data() == {"days": {"2026-10-03": True}}
    edit_text = callback.message.edits[0][0]
    assert edit_text == texts.DELETE_PROMPT.format(count=1)


async def test_delete_next_without_selection_alerts(tmp_path):
    callback = _FakeCallback(111)
    state = _FakeState({"days": {}})

    await delete_next_to_confirm(callback, state)

    assert any(args and args[0] == texts.ALERT_PICK_DELETE for args, _ in callback.answers)
    assert state.set_to is None


async def test_delete_next_with_selection_shows_confirmation(tmp_path):
    callback = _FakeCallback(111)
    state = _FakeState({"days": {"2026-10-04": True, "2026-10-03": True}})

    await delete_next_to_confirm(callback, state)

    assert state.set_to == AbsenceForm.delete_confirm
    edit_text = callback.message.edits[0][0]
    assert edit_text.startswith("🗑 03.10.2026 (сб)\n🗑 04.10.2026 (вс)")
    assert edit_text.endswith(texts.DELETE_QUESTION)


async def test_delete_back_returns_to_picker(tmp_path, monkeypatch):
    _fix_window(monkeypatch)
    storage = Storage(tmp_path)
    await storage.upsert_member(111, "Студент Тестовий", "student", status=MEMBER_APPROVED)
    await storage.upsert_absences_batch(111, ["2026-10-03"], "illness", None)
    callback = _FakeCallback(111)
    state = _FakeState({"days": {"2026-10-03": True}})

    await delete_back(callback, state, storage)

    assert state.set_to == AbsenceForm.delete_day
    edit_text = callback.message.edits[0][0]
    assert edit_text == texts.DELETE_PROMPT.format(count=1)


# --- confirm_delete ---


async def test_confirm_delete_removes_todays_record(tmp_path, monkeypatch):
    _fix_window(monkeypatch)
    storage = Storage(tmp_path)
    await storage.upsert_member(111, "Студент Тестовий", "student", status=MEMBER_APPROVED)
    await storage.upsert_absences_batch(111, ["2026-10-03"], "illness", None)
    callback = _FakeCallback(111)
    state = _FakeState({"days": {"2026-10-03": True}})

    await confirm_delete(callback, state, storage)

    assert state.cleared
    assert await storage.get_record(111, "2026-10-03") is None
    assert any(
        text == texts.DELETE_SUCCESS.format(dates="03.10")
        for text, _ in callback.message.answers
    )


async def test_confirm_delete_past_is_rejected_without_write(tmp_path, monkeypatch):
    _fix_window(monkeypatch)
    storage = Storage(tmp_path)
    await storage.upsert_member(111, "Студент Тестовий", "student", status=MEMBER_APPROVED)
    await storage.upsert_absences_batch(111, ["2026-10-02"], "illness", None)
    callback = _FakeCallback(111)
    state = _FakeState({"days": {"2026-10-02": True}})

    await confirm_delete(callback, state, storage)

    assert state.cleared
    assert await storage.get_record(111, "2026-10-02") is not None
    assert any(
        args and args[0] == texts.DELETE_PAST_REJECTED and kwargs.get("show_alert") is True
        for args, kwargs in callback.answers
    )


async def test_confirm_delete_out_of_window_alerts_stale(tmp_path, monkeypatch):
    _fix_window(monkeypatch)
    storage = Storage(tmp_path)
    await storage.upsert_member(111, "Студент Тестовий", "student", status=MEMBER_APPROVED)
    await storage.upsert_absences_batch(111, ["2026-10-10"], "illness", None)
    callback = _FakeCallback(111)
    state = _FakeState({"days": {"2026-10-10": True}})

    await confirm_delete(callback, state, storage)

    assert state.cleared
    assert await storage.get_record(111, "2026-10-10") is not None
    assert any(
        args and args[0] == texts.STALE_CALLBACK and kwargs.get("show_alert") is True
        for args, kwargs in callback.answers
    )


async def test_confirm_delete_rechecks_rights(tmp_path):
    storage = Storage(tmp_path)  # no roster entry → no rights at confirm time
    callback = _FakeCallback(111)
    state = _FakeState({"days": {"2026-10-03": True}})

    await confirm_delete(callback, state, storage)

    assert state.cleared
    assert any(
        args and args[0] == texts.NOT_ALLOWED_ABSENCE and kwargs.get("show_alert") is True
        for args, kwargs in callback.answers
    )
    assert await storage.get_record(111, "2026-10-03") is None


@pytest.mark.asyncio
async def test_confirm_delete_is_idempotent_when_record_already_gone(tmp_path, monkeypatch):
    _fix_window(monkeypatch)
    storage = Storage(tmp_path)
    await storage.upsert_member(111, "Студент Тестовий", "student", status=MEMBER_APPROVED)
    callback = _FakeCallback(111)
    state = _FakeState({"days": {"2026-10-03": True}})

    await confirm_delete(callback, state, storage)

    assert any(text == texts.DELETE_NOTHING for text, _ in callback.message.answers)
