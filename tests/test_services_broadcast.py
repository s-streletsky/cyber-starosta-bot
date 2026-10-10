"""Tests for services/broadcast.py: recipients, messages, validation, formatting."""

import pytest

import texts
from services.broadcast import (
    BROADCAST_MESSAGES,
    BROADCAST_TEXT_MAX,
    format_confirm,
    format_result,
    is_valid_message,
    message_text,
    resolve_recipients,
    validate_broadcast_text,
)
from services.members import member_label


def _member(display_name: str, username: str | None = None) -> dict:
    return {"display_name": display_name, "username": username}


def test_resolve_recipients_excludes_sender():
    members = [(1, _member("Іван")), (2, _member("Петро"))]

    recipients = resolve_recipients(members, sender_id=1)

    assert [user_id for user_id, _ in recipients] == [2]


def test_resolve_recipients_sorts_case_insensitively_with_id_tiebreak():
    members = [
        (3, _member("борис")),
        (2, _member("Аліса")),
        (1, _member("Аліса")),
    ]

    recipients = resolve_recipients(members, sender_id=99)

    assert [user_id for user_id, _ in recipients] == [1, 2, 3]


def test_is_valid_message_and_message_text():
    assert is_valid_message("reason_reminder") is True
    assert is_valid_message("nope") is False
    assert message_text("reason_reminder") == texts.BROADCAST_REASON_TEXT
    assert BROADCAST_MESSAGES[0].code == "reason_reminder"
    assert BROADCAST_MESSAGES[0].label == texts.BROADCAST_MSG_REASON_LABEL


@pytest.mark.parametrize("bad", ["", "   "])
def test_validate_broadcast_text_rejects_empty(bad):
    with pytest.raises(ValueError):
        validate_broadcast_text(bad)


def test_validate_broadcast_text_rejects_too_long():
    with pytest.raises(ValueError):
        validate_broadcast_text("а" * (BROADCAST_TEXT_MAX + 1))


def test_validate_broadcast_text_normalizes():
    assert validate_broadcast_text("  Привіт  ") == "Привіт"
    assert validate_broadcast_text("а" * BROADCAST_TEXT_MAX) == "а" * BROADCAST_TEXT_MAX


def test_format_confirm_lists_recipients_and_message():
    recipients = [(1, _member("Аліса", "alice"))]

    text = format_confirm(recipients, "Текст")

    assert "1" in text
    assert f"• {member_label(recipients[0][1])}" in text
    assert "Текст" in text
    assert texts.BROADCAST_CONFIRM_QUESTION in text


def test_format_result_clean_and_partial():
    assert format_result(3, 0) == texts.BROADCAST_SUCCESS.format(count=3)
    expected = texts.BROADCAST_SUCCESS_PARTIAL.format(delivered=2, failed=1)
    assert format_result(2, 1) == expected
