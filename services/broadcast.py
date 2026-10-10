"""Pure logic of the broadcast notifications flow: recipients, messages, formatting.

No aiogram — the module is covered by tests directly.
"""

from typing import Any, NamedTuple

import texts
from services.members import member_label


class BroadcastMessage(NamedTuple):
    code: str
    label: str
    text: str


# Keep broadcasts well under Telegram's 4096-character message limit.
BROADCAST_TEXT_MAX = 800

BROADCAST_MESSAGES: list[BroadcastMessage] = [
    BroadcastMessage(
        "reason_reminder", texts.BROADCAST_MSG_REASON_LABEL, texts.BROADCAST_REASON_TEXT
    ),
]

_MESSAGES_BY_CODE = {message.code: message for message in BROADCAST_MESSAGES}


def resolve_recipients(
    members: list[tuple[int, dict[str, Any]]], sender_id: int
) -> list[tuple[int, dict[str, Any]]]:
    """Approved members minus the sender, ordered by display_name.casefold() then user_id."""
    recipients = [
        (user_id, member) for user_id, member in members if user_id != sender_id
    ]
    recipients.sort(
        key=lambda pair: ((pair[1].get("display_name") or "").casefold(), pair[0])
    )
    return recipients


def is_valid_message(code: str) -> bool:
    """Whether the code belongs to the predefined broadcast messages."""
    return code in _MESSAGES_BY_CODE


def message_text(code: str) -> str:
    """Text of a predefined message by code (assumes the code was validated)."""
    return _MESSAGES_BY_CODE[code].text


def validate_broadcast_text(text: str) -> str:
    """Strip; ValueError if empty or longer than BROADCAST_TEXT_MAX characters."""
    cleaned = (text or "").strip()
    if not cleaned:
        raise ValueError("empty")
    if len(cleaned) > BROADCAST_TEXT_MAX:
        raise ValueError("too_long")
    return cleaned


def format_confirm(recipients: list[tuple[int, dict[str, Any]]], message: str) -> str:
    """Confirmation summary: recipient count, one «• label» line each, the text and the question."""
    names = "\n".join(f"• {member_label(member)}" for _, member in recipients)
    summary = texts.BROADCAST_CONFIRM.format(
        count=len(recipients), names=names, message=message
    )
    return f"{summary}\n\n{texts.BROADCAST_CONFIRM_QUESTION}"


def format_result(delivered: int, failed: int) -> str:
    """Clean success when nothing failed, otherwise a partial-delivery notice."""
    if failed == 0:
        return texts.BROADCAST_SUCCESS.format(count=delivered)
    return texts.BROADCAST_SUCCESS_PARTIAL.format(delivered=delivered, failed=failed)
