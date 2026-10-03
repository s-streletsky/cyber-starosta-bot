"""Unit tests for handlers/absence.py: FSM flow for marking absence."""

from datetime import date

import pytest

import texts
from callbacks import DayCb, ReasonCb
from config import TZ
from handlers.absence import (
    AbsenceForm,
    cancel_flow,
    cancel_other_text,
    choose_reason,
    confirm_back,
    confirm_send,
    next_to_reason,
    receive_other_text,
    start_absence,
    toggle_day,
)
from services.absence import REASON_TEXT_MAX, build_days
from storage import MEMBER_APPROVED, Storage
from tests.fakes import _FakeCallback, _FakeMessage, _FakeState, _reply_button_texts


@pytest.mark.parametrize(
    ("user_id", "make_lead"),
    [
        (111, True),  # group_lead student
        (999999999, False),  # env admin (ADMIN_USER_IDS from conftest)
    ],
)
async def test_confirm_send_keeps_reports_button_for_lead_and_admin(
    tmp_path, user_id, make_lead, monkeypatch
):
    storage = Storage(tmp_path)
    if make_lead:
        await storage.upsert_member(
            user_id, "Лід Групи", "lead", status=MEMBER_APPROVED
        )
        await storage.add_role(user_id, "group_lead")

    fixed_days = build_days(TZ, today=date(2026, 10, 1))
    monkeypatch.setattr("handlers.absence.build_days", lambda tz: fixed_days)

    callback = _FakeCallback(user_id)
    today = fixed_days[0]["day"].isoformat()
    state = _FakeState(
        {
            "days": {today: True},
            "reason_code": "illness",
            "reason_text": None,
        }
    )

    await confirm_send(callback, state, storage)

    assert callback.message.answers, "confirm_send must reply with the success message"
    _, markup = callback.message.answers[0]
    assert texts.MENU_REPORTS in _reply_button_texts(markup)


# --- start_absence ---


@pytest.mark.asyncio
async def test_start_absence_denied_for_non_approved(tmp_path):
    storage = Storage(tmp_path)
    msg = _FakeMessage(from_user_id=111)
    state = _FakeState()

    await start_absence(msg, state, storage)

    assert any(texts.NOT_ALLOWED_ABSENCE == text for text, _ in msg.answers)
    assert state.set_to is None


@pytest.mark.asyncio
async def test_start_absence_starts_day_step(tmp_path):
    storage = Storage(tmp_path)
    await storage.upsert_member(111, "Студент Тестовий", "student", status=MEMBER_APPROVED)
    msg = _FakeMessage(from_user_id=111)
    state = _FakeState()

    await start_absence(msg, state, storage)

    assert state.set_to == AbsenceForm.day
    assert len(msg.answers) == 1
    assert texts.DAY_PROMPT.split("{")[0] in msg.answers[0][0]


@pytest.mark.asyncio
async def test_confirm_send_denied_for_supervisor_or_missing(tmp_path):
    storage = Storage(tmp_path)
    callback = _FakeCallback(111)
    state = _FakeState(
        {
            "days": {"2026-10-01": True},
            "reason_code": "illness",
            "reason_text": None,
        }
    )

    await confirm_send(callback, state, storage)

    assert state.cleared
    assert any(
        args
        and args[0] == texts.NOT_ALLOWED_ABSENCE
        and kwargs.get("show_alert") is True
        for args, kwargs in callback.answers
    )
    assert await storage.get_record(111, "2026-10-01") is None


async def test_confirm_send_stale_selection_clears_and_alerts(tmp_path, monkeypatch):
    storage = Storage(tmp_path)
    await storage.upsert_member(111, "Студент Тестовий", "student", status=MEMBER_APPROVED)

    fixed_days = build_days(TZ, today=date(2026, 10, 1))
    monkeypatch.setattr("handlers.absence.build_days", lambda tz: fixed_days)

    callback = _FakeCallback(111)
    state = _FakeState(
        {
            "days": {"2026-09-30": True},
            "reason_code": "illness",
            "reason_text": None,
        }
    )

    await confirm_send(callback, state, storage)

    assert state.cleared
    assert any(
        args and args[0] == texts.STALE_CALLBACK and kwargs.get("show_alert") is True
        for args, kwargs in callback.answers
    )
    assert await storage.get_record(111, "2026-09-30") is None


# --- FSM handlers ---


# 10. toggle_day: empty state → day toggled, view redrawn
@pytest.mark.asyncio
async def test_toggle_day(tmp_path):
    callback = _FakeCallback(111)
    state = _FakeState()
    callback_data = DayCb(date="2026-10-01")

    await toggle_day(callback, state, callback_data)

    assert len(callback.answers) == 1
    assert len(callback.message.edits) == 1
    edit_text = callback.message.edits[0][0]
    assert texts.DAY_PROMPT.split("{")[0] in edit_text


# 11. next_to_reason with no days → alert, state unchanged
@pytest.mark.asyncio
async def test_next_to_reason_no_days(tmp_path):
    callback = _FakeCallback(111)
    state = _FakeState()

    await next_to_reason(callback, state)

    assert any(
        args and args[0] == texts.ALERT_PICK_DAY for args, _ in callback.answers
    )
    assert state.set_to is None


# 12. next_to_reason with a day selected → moves to reason step
@pytest.mark.asyncio
async def test_next_to_reason_with_days(tmp_path):
    callback = _FakeCallback(111)
    state = _FakeState({"days": {"2026-10-01": True}})

    await next_to_reason(callback, state)

    assert state.set_to == AbsenceForm.reason
    assert len(callback.message.edits) == 1
    edit_text = callback.message.edits[0][0]
    assert texts.REASON_PROMPT.split("{")[0] in edit_text


# 13. cancel_flow: state cleared, cancelled message sent (covers day/reason/confirm states)
@pytest.mark.parametrize("extra_data", [{}, {"reason_code": "illness"}])
@pytest.mark.asyncio
async def test_cancel_flow(tmp_path, extra_data):
    storage = Storage(tmp_path)
    callback = _FakeCallback(111)
    state = _FakeState({"days": {"2026-10-01": True}, **extra_data})

    await cancel_flow(callback, state, storage)

    assert state.cleared
    assert len(callback.answers) == 1
    assert len(callback.message.answers) == 1
    assert texts.CANCELLED in callback.message.answers[0][0]


# 14. choose_reason "other" → moves to free-text step
@pytest.mark.asyncio
async def test_choose_reason_other(tmp_path):
    storage = Storage(tmp_path)
    callback = _FakeCallback(111)
    state = _FakeState({"days": {"2026-10-01": True}})
    callback_data = ReasonCb(code="other")

    await choose_reason(callback, state, storage, callback_data)

    assert state.set_to == AbsenceForm.other_text
    assert len(callback.message.edits) == 1
    assert texts.OTHER_TEXT_PROMPT.format(limit=REASON_TEXT_MAX) in callback.message.edits[0][0]


# 15. choose_reason "back" → returns to day step
@pytest.mark.asyncio
async def test_choose_reason_back(tmp_path):
    storage = Storage(tmp_path)
    callback = _FakeCallback(111)
    state = _FakeState({"days": {"2026-10-01": True}})
    callback_data = ReasonCb(code="back")

    await choose_reason(callback, state, storage, callback_data)

    assert state.set_to == AbsenceForm.day
    assert len(callback.message.edits) == 1
    edit_text = callback.message.edits[0][0]
    assert texts.DAY_PROMPT.split("{")[0] in edit_text


# 16. choose_reason with a valid code → moves to confirm step
@pytest.mark.asyncio
async def test_choose_reason_valid(tmp_path):
    storage = Storage(tmp_path)
    callback = _FakeCallback(111)
    state = _FakeState({"days": {"2026-10-01": True}})
    callback_data = ReasonCb(code="illness")

    await choose_reason(callback, state, storage, callback_data)

    assert state.set_to == AbsenceForm.confirm
    assert len(callback.message.edits) == 1
    edit_text = callback.message.edits[0][0]
    assert texts.CONFIRM_QUESTION in edit_text


# 17. cancel_other_text: /cancel clears state, sends cancelled
@pytest.mark.asyncio
async def test_cancel_other_text(tmp_path):
    storage = Storage(tmp_path)
    msg = _FakeMessage(from_user_id=111)
    state = _FakeState()

    await cancel_other_text(msg, state, storage)

    assert state.cleared
    assert len(msg.answers) == 1
    assert texts.CANCELLED in msg.answers[0][0]


# 18. receive_other_text valid → moves to confirm step
@pytest.mark.asyncio
async def test_receive_other_text_valid(tmp_path):
    storage = Storage(tmp_path)
    msg = _FakeMessage(from_user_id=111, text="сімейні справи")
    state = _FakeState({"days": {"2026-10-01": True}})

    await receive_other_text(msg, state, storage)

    assert state.set_to == AbsenceForm.confirm
    assert len(msg.answers) == 1
    assert texts.CONFIRM_QUESTION in msg.answers[0][0]


# 19. receive_other_text empty → error, stays in flow
@pytest.mark.asyncio
async def test_receive_other_text_empty(tmp_path):
    storage = Storage(tmp_path)
    msg = _FakeMessage(from_user_id=111, text="")
    state = _FakeState({"days": {"2026-10-01": True}})

    await receive_other_text(msg, state, storage)

    assert state.set_to is None
    assert len(msg.answers) == 1
    assert texts.OTHER_TEXT_EMPTY.format(limit=REASON_TEXT_MAX) in msg.answers[0][0]


# 20. receive_other_text too long → error, stays in flow
@pytest.mark.asyncio
async def test_receive_other_text_too_long(tmp_path):
    storage = Storage(tmp_path)
    msg = _FakeMessage(from_user_id=111, text="а" * (REASON_TEXT_MAX + 1))
    state = _FakeState({"days": {"2026-10-01": True}})

    await receive_other_text(msg, state, storage)

    assert state.set_to is None
    assert len(msg.answers) == 1
    assert texts.OTHER_TEXT_TOO_LONG.format(limit=REASON_TEXT_MAX) in msg.answers[0][0]


# 21. confirm_back: returns to day step
@pytest.mark.asyncio
async def test_confirm_back(tmp_path):
    callback = _FakeCallback(111)
    state = _FakeState({"days": {"2026-10-01": True}, "reason_code": "illness"})

    await confirm_back(callback, state)

    assert state.set_to == AbsenceForm.day
    assert len(callback.message.edits) == 1
    edit_text = callback.message.edits[0][0]
    assert texts.DAY_PROMPT.split("{")[0] in edit_text



