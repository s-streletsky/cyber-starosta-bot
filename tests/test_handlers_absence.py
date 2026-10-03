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
from storage import ABSENCE_ATTEMPT_LIMIT, ABSENCE_CREATED, MEMBER_APPROVED, Storage
from tests.fakes import (
    _FakeCallback,
    _FakeMessage,
    _FakeState,
    _inline_button_texts,
    _reply_button_texts,
)


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


# --- per-date mutation attempt limit ---


async def test_confirm_send_all_blocked_alerts_limit_and_writes_nothing(tmp_path, monkeypatch):
    storage = Storage(tmp_path)
    await storage.upsert_member(111, "Студент Тестовий", "student", status=MEMBER_APPROVED)
    fixed_days = build_days(TZ, today=date(2026, 10, 1))
    monkeypatch.setattr("handlers.absence.build_days", lambda tz: fixed_days)
    blocked_day = fixed_days[0]["day"].isoformat()
    for index in range(ABSENCE_ATTEMPT_LIMIT):
        await storage.upsert_absences_batch(111, [blocked_day], "illness", f"text-{index}")
    lines_before = (tmp_path / "absences.jsonl").read_text(encoding="utf-8").splitlines()

    callback = _FakeCallback(111)
    state = _FakeState(
        {"days": {blocked_day: True}, "reason_code": "family", "reason_text": None}
    )

    await confirm_send(callback, state, storage)

    assert state.cleared
    expected = texts.LIMIT_REACHED.format(limit=ABSENCE_ATTEMPT_LIMIT, dates="01.10")
    assert any(
        args and args[0] == expected and kwargs.get("show_alert") is True
        for args, kwargs in callback.answers
    )
    assert callback.message.answers == []
    lines_after = (tmp_path / "absences.jsonl").read_text(encoding="utf-8").splitlines()
    assert lines_after == lines_before


async def test_confirm_send_partial_reports_allowed_and_blocked(tmp_path, monkeypatch):
    storage = Storage(tmp_path)
    await storage.upsert_member(111, "Студент Тестовий", "student", status=MEMBER_APPROVED)
    fixed_days = build_days(TZ, today=date(2026, 10, 1))
    monkeypatch.setattr("handlers.absence.build_days", lambda tz: fixed_days)
    blocked_day = fixed_days[0]["day"].isoformat()
    free_day = fixed_days[1]["day"].isoformat()
    for index in range(ABSENCE_ATTEMPT_LIMIT):
        await storage.upsert_absences_batch(111, [blocked_day], "illness", f"text-{index}")

    callback = _FakeCallback(111)
    state = _FakeState(
        {
            "days": {blocked_day: True, free_day: True},
            "reason_code": "family",
            "reason_text": None,
        }
    )

    await confirm_send(callback, state, storage)

    success = texts.SUCCESS.format(dates="02.10", reason="сімейні обставини")
    partial = texts.LIMIT_REACHED_PARTIAL.format(limit=ABSENCE_ATTEMPT_LIMIT, dates="01.10")
    assert any(text.startswith(success) and partial in text for text, _ in callback.message.answers)
    assert await storage.get_record(111, free_day) is not None
    assert await storage.get_record(111, blocked_day) is not None


async def test_confirm_send_mixed_limit_and_identical_has_no_false_alert(tmp_path, monkeypatch):
    """Defect A: one date at the cap plus one identical no-op must not alert."""
    storage = Storage(tmp_path)
    await storage.upsert_member(111, "Студент Тестовий", "student", status=MEMBER_APPROVED)
    fixed_days = build_days(TZ, today=date(2026, 10, 1))
    monkeypatch.setattr("handlers.absence.build_days", lambda tz: fixed_days)
    blocked_day = fixed_days[0]["day"].isoformat()
    identical_day = fixed_days[1]["day"].isoformat()
    for index in range(ABSENCE_ATTEMPT_LIMIT):
        await storage.upsert_absences_batch(111, [blocked_day], "family", f"seed-{index}")
    await storage.upsert_absences_batch(111, [identical_day], "illness", None)

    callback = _FakeCallback(111)
    state = _FakeState(
        {
            "days": {blocked_day: True, identical_day: True},
            "reason_code": "illness",
            "reason_text": None,
        }
    )

    await confirm_send(callback, state, storage)

    assert not any(kwargs.get("show_alert") for _, kwargs in callback.answers)
    assert callback.message.answers, "the normal no-op result is still sent"
    text = callback.message.answers[0][0]
    # The identical date is reported as marked; the blocked date is not.
    success = texts.SUCCESS.format(dates="02.10", reason="хвороба")
    assert success in text
    # The blocked date must not be claimed as marked in the success message.
    assert "Позначено: 01.10" not in text
    # The blocked date is disclosed via the partial limit notice.
    partial = texts.LIMIT_REACHED_PARTIAL.format(limit=ABSENCE_ATTEMPT_LIMIT, dates="01.10")
    assert partial in text


async def test_confirm_view_blocks_non_admin_at_limit(tmp_path, monkeypatch):
    """Defect B (control): a non-admin at the cap still sees the gate."""
    storage = Storage(tmp_path)
    await storage.upsert_member(111, "Студент Тестовий", "student", status=MEMBER_APPROVED)
    fixed_days = build_days(TZ, today=date(2026, 10, 1))
    monkeypatch.setattr("handlers.absence.build_days", lambda tz: fixed_days)
    day = fixed_days[0]["day"].isoformat()
    for index in range(ABSENCE_ATTEMPT_LIMIT):
        await storage.upsert_absences_batch(111, [day], "family", f"seed-{index}")

    callback = _FakeCallback(111)
    state = _FakeState({"days": {day: True}})

    await choose_reason(callback, state, storage, ReasonCb(code="illness"))

    text, markup = callback.message.edits[0]
    assert texts.LIMIT_REACHED.format(limit=ABSENCE_ATTEMPT_LIMIT, dates="01.10") in text
    assert texts.CONFIRM_QUESTION not in text
    buttons = _inline_button_texts(markup)
    assert texts.BUTTON_SEND not in buttons
    assert texts.BUTTON_SEND_REPLACE not in buttons


async def test_confirm_view_admin_at_limit_gets_normal_send(tmp_path, monkeypatch):
    """Defect B: an env admin at the cap skips the gate and gets the send button."""
    storage = Storage(tmp_path)
    fixed_days = build_days(TZ, today=date(2026, 10, 1))
    monkeypatch.setattr("handlers.absence.build_days", lambda tz: fixed_days)
    day = fixed_days[0]["day"].isoformat()
    for index in range(ABSENCE_ATTEMPT_LIMIT):
        await storage.upsert_absences_batch(999999999, [day], "family", f"seed-{index}")

    callback = _FakeCallback(999999999)  # env admin from conftest
    state = _FakeState({"days": {day: True}})

    await choose_reason(callback, state, storage, ReasonCb(code="illness"))

    text, markup = callback.message.edits[0]
    assert texts.CONFIRM_QUESTION in text
    assert texts.LIMIT_REACHED not in text
    buttons = _inline_button_texts(markup)
    assert texts.BUTTON_SEND in buttons or texts.BUTTON_SEND_REPLACE in buttons


async def test_confirm_send_admin_bypasses_limit(tmp_path, monkeypatch):
    storage = Storage(tmp_path)
    fixed_days = build_days(TZ, today=date(2026, 10, 1))
    monkeypatch.setattr("handlers.absence.build_days", lambda tz: fixed_days)
    day = fixed_days[0]["day"].isoformat()

    captured: dict[str, bool] = {}

    async def fake_upsert(user_id, dates, reason, reason_text, enforce_limit=True):
        captured["enforce_limit"] = enforce_limit
        return [ABSENCE_CREATED for _ in dates]

    monkeypatch.setattr(storage, "upsert_absences_batch", fake_upsert)

    callback = _FakeCallback(999999999)  # env admin from conftest
    state = _FakeState({"days": {day: True}, "reason_code": "illness", "reason_text": None})

    await confirm_send(callback, state, storage)

    assert captured["enforce_limit"] is False



