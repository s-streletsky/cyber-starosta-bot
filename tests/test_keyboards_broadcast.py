"""Tests for keyboards/broadcast.py: broadcast flow inline keyboards."""

import texts
from callbacks import (
    ACTION_ALL,
    ACTION_BACK,
    ACTION_CANCEL,
    ACTION_CUSTOM,
    ACTION_NEXT,
    ACTION_SEND,
    BroadcastCtl,
    ConfirmCb,
    MessageCb,
    RecipientCb,
)
from keyboards.broadcast import (
    broadcast_confirm_keyboard,
    message_keyboard,
    recipient_keyboard,
)
from services.broadcast import BROADCAST_MESSAGES
from services.members import member_label


def _member(display_name: str, username: str | None = None) -> dict:
    return {"display_name": display_name, "username": username}


def _recipients():
    return [(1, _member("Аліса", "alice")), (2, _member("Богдан"))]


def test_recipient_keyboard_rows_and_markers():
    recipients = _recipients()

    rows = recipient_keyboard(recipients, {"1"}).inline_keyboard

    assert rows[0][0].text == texts.BROADCAST_ALL_BUTTON
    assert BroadcastCtl.unpack(rows[0][0].callback_data).action == ACTION_ALL

    assert rows[1][0].text == texts.BROADCAST_MARKER_SELECTED + member_label(recipients[0][1])
    assert RecipientCb.unpack(rows[1][0].callback_data).user_id == 1
    assert rows[2][0].text == texts.BROADCAST_MARKER_UNSELECTED + member_label(recipients[1][1])
    assert RecipientCb.unpack(rows[2][0].callback_data).user_id == 2

    control = rows[-1]
    assert [button.text for button in control] == [texts.BUTTON_CANCEL, texts.BUTTON_NEXT]
    assert BroadcastCtl.unpack(control[0].callback_data).action == ACTION_CANCEL
    assert BroadcastCtl.unpack(control[1].callback_data).action == ACTION_NEXT


def test_recipient_keyboard_all_button_marks_when_all_selected():
    rows = recipient_keyboard(_recipients(), {"1", "2"}).inline_keyboard

    assert rows[0][0].text == texts.BROADCAST_MARKER_SELECTED + texts.BROADCAST_ALL_BUTTON


def test_message_keyboard_predefined_custom_and_controls():
    rows = message_keyboard().inline_keyboard
    first = BROADCAST_MESSAGES[0]

    assert rows[0][0].text == first.label
    assert MessageCb.unpack(rows[0][0].callback_data).code == first.code

    custom_row = rows[len(BROADCAST_MESSAGES)]
    assert custom_row[0].text == texts.BROADCAST_CUSTOM_BUTTON
    assert MessageCb.unpack(custom_row[0].callback_data).code == ACTION_CUSTOM

    control = rows[-1]
    assert [button.text for button in control] == [texts.BUTTON_CANCEL, texts.BUTTON_BACK]
    assert BroadcastCtl.unpack(control[0].callback_data).action == ACTION_CANCEL
    assert MessageCb.unpack(control[1].callback_data).code == ACTION_BACK


def test_broadcast_confirm_keyboard():
    rows = broadcast_confirm_keyboard().inline_keyboard

    assert [button.text for button in rows[0]] == [texts.BUTTON_SEND]
    assert ConfirmCb.unpack(rows[0][0].callback_data).action == ACTION_SEND
    assert [button.text for button in rows[1]] == [texts.BUTTON_CANCEL, texts.BUTTON_BACK]
    assert BroadcastCtl.unpack(rows[1][0].callback_data).action == ACTION_CANCEL
    assert ConfirmCb.unpack(rows[1][1].callback_data).action == ACTION_BACK
