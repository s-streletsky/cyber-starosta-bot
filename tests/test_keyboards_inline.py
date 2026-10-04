"""Tests for the inline keyboards: callback_data round-trips and text labels."""

from datetime import date

import texts
from callbacks import (
    ACTION_BACK,
    ACTION_CANCEL,
    ACTION_NEXT,
    ACTION_SEND,
    ADMIN_SET_ROLE,
    APPROVE_ACCEPT,
    APPROVE_REJECT,
    DELETE_CONFIRM,
    REPORT_TODAY,
    AdminCb,
    ApproveCb,
    ConfirmCb,
    DayCb,
    DayCtl,
    DeleteCb,
    ReasonCb,
    ReportCb,
)
from keyboards.absence import (
    back_keyboard,
    confirm_keyboard,
    day_keyboard,
    delete_confirm_keyboard,
    reason_keyboard,
)
from keyboards.admin import person_list_keyboard, role_choice_keyboard
from keyboards.approvals import request_keyboard
from keyboards.report import report_menu_keyboard
from services.absence import REASONS
from storage import ROLE_GROUP_LEAD, ROLE_SUPERVISOR


def _buttons(markup) -> list:
    return [button for row in markup.inline_keyboard for button in row]


def test_day_keyboard_round_trips_and_labels():
    days = [
        {"day": date(2026, 10, 1), "label": "Сьогодні, 01.10 (чт)"},
        {"day": date(2026, 10, 2), "label": "Завтра, 02.10 (пт)"},
    ]

    rows = day_keyboard(days, {"2026-10-01"}).inline_keyboard

    assert rows[0][0].text == texts.DAY_MARKER_SELECTED + days[0]["label"]
    assert DayCb.unpack(rows[0][0].callback_data).date == "2026-10-01"
    assert rows[1][0].text == texts.DAY_MARKER_UNSELECTED + days[1]["label"]
    assert DayCb.unpack(rows[1][0].callback_data).date == "2026-10-02"

    assert len(rows) == 3
    control = rows[-1]
    assert [button.text for button in control] == [texts.BUTTON_CANCEL, texts.BUTTON_NEXT]
    assert DayCtl.unpack(control[0].callback_data).action == ACTION_CANCEL
    assert DayCtl.unpack(control[1].callback_data).action == ACTION_NEXT


def test_reason_keyboard_round_trips_and_labels():
    markup = reason_keyboard()
    rows = markup.inline_keyboard
    reason_codes = [code for code, _ in REASONS]

    reason_buttons = _buttons(markup)[: len(REASONS)]
    assert [button.text for button in reason_buttons] == [label for _, label in REASONS]
    assert [ReasonCb.unpack(button.callback_data).code for button in reason_buttons] == reason_codes

    reason_rows = rows[:-1]
    assert len(reason_rows) == (len(REASONS) + 1) // 2
    assert all(len(row) == 2 for row in reason_rows[:-1])
    assert len(reason_rows[-1]) == (1 if len(REASONS) % 2 else 2)

    control = rows[-1]
    assert [button.text for button in control] == [texts.BUTTON_CANCEL, texts.BUTTON_BACK]
    assert DayCtl.unpack(control[0].callback_data).action == ACTION_CANCEL
    assert ReasonCb.unpack(control[1].callback_data).code == ACTION_BACK


def test_confirm_keyboard_send_and_back():
    rows = confirm_keyboard(has_replaced=False).inline_keyboard

    assert [button.text for button in rows[0]] == [texts.BUTTON_SEND]
    assert ConfirmCb.unpack(rows[0][0].callback_data).action == ACTION_SEND
    assert [button.text for button in rows[1]] == [texts.BUTTON_CANCEL, texts.BUTTON_BACK]
    assert DayCtl.unpack(rows[1][0].callback_data).action == ACTION_CANCEL
    assert ConfirmCb.unpack(rows[1][1].callback_data).action == ACTION_BACK
    assert len(rows) == 2


def test_confirm_keyboard_uses_replace_label_when_needed():
    rows = confirm_keyboard(has_replaced=True).inline_keyboard

    assert rows[0][0].text == texts.BUTTON_SEND_REPLACE


def test_back_keyboard_round_trips():
    rows = back_keyboard().inline_keyboard

    assert len(rows) == 1
    assert rows[0][0].text == texts.BUTTON_BACK
    assert ConfirmCb.unpack(rows[0][0].callback_data).action == ACTION_BACK


def test_delete_confirm_keyboard_round_trips():
    rows = delete_confirm_keyboard().inline_keyboard

    assert [button.text for button in rows[0]] == [texts.BUTTON_DELETE]
    assert DeleteCb.unpack(rows[0][0].callback_data).action == DELETE_CONFIRM
    assert [button.text for button in rows[1]] == [texts.BUTTON_CANCEL, texts.BUTTON_BACK]
    assert DayCtl.unpack(rows[1][0].callback_data).action == ACTION_CANCEL
    assert DeleteCb.unpack(rows[1][1].callback_data).action == ACTION_BACK
    assert len(rows) == 2


def test_person_list_keyboard_round_trips_and_marks_head_lead():
    people = [
        (1, {"display_name": "Аліса", "username": "alice"}),
        (2, {"display_name": "Богдан", "username": None}),
    ]

    buttons = _buttons(person_list_keyboard(people, "remove", head_lead_id=2))

    assert buttons[0].text == "Аліса (@alice)"
    parsed = AdminCb.unpack(buttons[0].callback_data)
    assert parsed.action == "remove"
    assert parsed.user_id == 1
    assert buttons[1].text == texts.HEAD_LEAD_CROWN + "Богдан"
    assert AdminCb.unpack(buttons[1].callback_data).user_id == 2


def test_role_choice_keyboard_round_trips():
    buttons = _buttons(role_choice_keyboard(7))

    assert buttons[0].text == texts.BUTTON_ROLE_GROUP_LEAD
    parsed = AdminCb.unpack(buttons[0].callback_data)
    assert parsed.action == ADMIN_SET_ROLE
    assert parsed.user_id == 7
    assert parsed.role == ROLE_GROUP_LEAD

    assert buttons[1].text == texts.BUTTON_ROLE_SUPERVISOR
    parsed = AdminCb.unpack(buttons[1].callback_data)
    assert parsed.role == ROLE_SUPERVISOR


def test_request_keyboard_round_trips():
    buttons = _buttons(request_keyboard(42))

    assert buttons[0].text == texts.BUTTON_ACCEPT
    parsed = ApproveCb.unpack(buttons[0].callback_data)
    assert parsed.action == APPROVE_ACCEPT
    assert parsed.user_id == 42

    assert buttons[1].text == texts.BUTTON_REJECT
    parsed = ApproveCb.unpack(buttons[1].callback_data)
    assert parsed.action == APPROVE_REJECT
    assert parsed.user_id == 42


def test_report_menu_keyboard_round_trips():
    buttons = _buttons(report_menu_keyboard())

    assert buttons[0].text == texts.REPORT_TODAY_BUTTON
    assert ReportCb.unpack(buttons[0].callback_data).action == REPORT_TODAY
