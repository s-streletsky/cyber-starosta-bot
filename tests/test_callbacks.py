"""Tests for CallbackData factories: callback_data formats from the spec."""

from typing import get_args

import pytest

import callbacks
from callbacks import (
    AdminCb,
    ApproveCb,
    BroadcastCtl,
    ConfirmCb,
    DayCb,
    DayCtl,
    DeleteCb,
    MessageCb,
    ReasonCb,
    RecipientCb,
    ReportCb,
)


def test_day_callback_format():
    assert DayCb(date="2026-09-29").pack() == "d:2026-09-29"
    assert DayCb.unpack("d:2026-09-29").date == "2026-09-29"


def test_day_control_callbacks_format():
    assert DayCtl(action="next").pack() == "dc:next"
    assert DayCtl(action="cancel").pack() == "dc:cancel"


def test_reason_callbacks_format():
    assert ReasonCb(code="illness").pack() == "r:illness"
    assert ReasonCb(code="other").pack() == "r:other"
    assert ReasonCb(code="back").pack() == "r:back"


def test_confirm_callbacks_format():
    assert ConfirmCb(action="send").pack() == "c:send"
    assert ConfirmCb(action="back").pack() == "c:back"


def test_foreign_callback_data_is_not_ours():
    # A foreign prefix is not parsed by our factory → such a callback goes to the stale handler.
    with pytest.raises(ValueError):
        DayCb.unpack("r:illness")


def test_approve_callbacks_format():
    assert ApproveCb(action="accept", user_id=42).pack() == "ar:accept:42"
    parsed = ApproveCb.unpack("ar:reject:42")
    assert parsed.action == "reject"
    assert parsed.user_id == 42


def test_admin_callbacks_format():
    # A None role is packed as an empty segment (this is what aiogram does for nullable fields).
    assert AdminCb(action="sethead", user_id=7).pack() == "adm:sethead:7:"
    parsed = AdminCb.unpack("adm:sethead:7:")
    assert parsed.action == "sethead"
    assert parsed.user_id == 7
    assert parsed.role is None

    parsed = AdminCb.unpack("adm:set_role:7:group_lead")
    assert parsed.action == "set_role"
    assert parsed.user_id == 7
    assert parsed.role == "group_lead"


def test_admin_callbacks_within_64_bytes():
    # The longest values must not exceed the Telegram limit.
    packed = AdminCb(action="pick_promote", user_id=9999999999, role="group_lead").pack()
    assert len(packed.encode()) <= 64


def test_report_callback_format():
    assert ReportCb(action="today").pack() == "rep:today"
    assert ReportCb.unpack("rep:today").action == "today"


def test_delete_callback_format():
    assert DeleteCb(action="confirm").pack() == "dl:confirm"
    assert DeleteCb(action="back").pack() == "dl:back"
    assert DeleteCb.unpack("dl:confirm").action == "confirm"


def test_delete_callback_within_64_bytes():
    assert len(DeleteCb(action="confirm").pack().encode()) <= 64


def test_recipient_callback_format():
    assert RecipientCb(user_id=123).pack() == "br:123"
    assert RecipientCb.unpack("br:123").user_id == 123


def test_broadcast_ctl_callback_format():
    assert BroadcastCtl(action="all").pack() == "bc:all"
    assert BroadcastCtl(action="next").pack() == "bc:next"
    assert BroadcastCtl(action="cancel").pack() == "bc:cancel"
    assert BroadcastCtl.unpack("bc:next").action == "next"


def test_message_callback_format():
    assert MessageCb(code="test").pack() == "bm:test"
    assert MessageCb(code="custom").pack() == "bm:custom"
    assert MessageCb(code="back").pack() == "bm:back"
    assert MessageCb.unpack("bm:test").code == "test"


def test_broadcast_callbacks_within_64_bytes():
    assert len(RecipientCb(user_id=9999999999).pack().encode()) <= 64
    assert len(BroadcastCtl(action="cancel").pack().encode()) <= 64
    assert len(MessageCb(code="custom").pack().encode()) <= 64


# --- literal/constant contract: the inline Literal strings must match the constants ---


def test_admin_action_literal_matches_constants():
    assert set(get_args(callbacks.AdminAction)) == {
        callbacks.ADMIN_PICK_PROMOTE,
        callbacks.ADMIN_SET_ROLE,
        callbacks.ADMIN_DEMOTE,
        callbacks.ADMIN_REMOVE,
        callbacks.ADMIN_SET_HEAD,
    }


def test_day_ctl_literal_matches_constants():
    assert set(get_args(DayCtl.model_fields["action"].annotation)) == {
        callbacks.ACTION_NEXT,
        callbacks.ACTION_CANCEL,
    }


def test_confirm_literal_matches_constants():
    assert set(get_args(ConfirmCb.model_fields["action"].annotation)) == {
        callbacks.ACTION_SEND,
        callbacks.ACTION_BACK,
    }


def test_approve_literal_matches_constants():
    assert set(get_args(ApproveCb.model_fields["action"].annotation)) == {
        callbacks.APPROVE_ACCEPT,
        callbacks.APPROVE_REJECT,
    }


def test_report_literal_matches_constants():
    assert set(get_args(ReportCb.model_fields["action"].annotation)) == {callbacks.REPORT_TODAY}


def test_delete_literal_matches_constants():
    assert set(get_args(DeleteCb.model_fields["action"].annotation)) == {
        callbacks.DELETE_CONFIRM,
        callbacks.ACTION_BACK,
    }


def test_broadcast_ctl_literal_matches_constants():
    assert set(get_args(BroadcastCtl.model_fields["action"].annotation)) == {
        callbacks.ACTION_ALL,
        callbacks.ACTION_NEXT,
        callbacks.ACTION_CANCEL,
    }
