"""Inline keyboards for the broadcast notifications flow."""

from typing import Any

from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup

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
from services.broadcast import BROADCAST_MESSAGES
from services.members import member_label


def recipient_keyboard(
    members: list[tuple[int, dict[str, Any]]], selected: set[str]
) -> InlineKeyboardMarkup:
    """One row per member; then «Усім студентам» (✅ when all are selected);
    last row: a shared row «Cancel» and «Next»."""
    rows: list[list[InlineKeyboardButton]] = []

    all_selected = bool(members) and all(
        str(user_id) in selected for user_id, _ in members
    )
    all_marker = texts.BROADCAST_MARKER_SELECTED if all_selected else ""

    for user_id, member in members:
        marker = (
            texts.BROADCAST_MARKER_SELECTED
            if str(user_id) in selected
            else texts.BROADCAST_MARKER_UNSELECTED
        )
        rows.append(
            [
                InlineKeyboardButton(
                    text=marker + member_label(member),
                    callback_data=RecipientCb(user_id=user_id).pack(),
                )
            ]
        )

    rows.append(
        [
            InlineKeyboardButton(
                text=all_marker + texts.BROADCAST_ALL_BUTTON,
                callback_data=BroadcastCtl(action=ACTION_ALL).pack(),
            )
        ]
    )

    rows.append(
        [
            InlineKeyboardButton(
                text=texts.BUTTON_CANCEL,
                callback_data=BroadcastCtl(action=ACTION_CANCEL).pack(),
            ),
            InlineKeyboardButton(
                text=texts.BUTTON_NEXT,
                callback_data=BroadcastCtl(action=ACTION_NEXT).pack(),
            ),
        ]
    )
    return InlineKeyboardMarkup(inline_keyboard=rows)


def message_keyboard() -> InlineKeyboardMarkup:
    """One row per predefined message, then «Своє повідомлення»;
    last row: a shared row «Cancel» and «Back»."""
    rows: list[list[InlineKeyboardButton]] = []
    for message in BROADCAST_MESSAGES:
        rows.append(
            [
                InlineKeyboardButton(
                    text=message.label,
                    callback_data=MessageCb(code=message.code).pack(),
                )
            ]
        )
    rows.append(
        [
            InlineKeyboardButton(
                text=texts.BROADCAST_CUSTOM_BUTTON,
                callback_data=MessageCb(code=ACTION_CUSTOM).pack(),
            )
        ]
    )
    rows.append(
        [
            InlineKeyboardButton(
                text=texts.BUTTON_CANCEL,
                callback_data=BroadcastCtl(action=ACTION_CANCEL).pack(),
            ),
            InlineKeyboardButton(
                text=texts.BUTTON_BACK,
                callback_data=MessageCb(code=ACTION_BACK).pack(),
            ),
        ]
    )
    return InlineKeyboardMarkup(inline_keyboard=rows)


def broadcast_confirm_keyboard() -> InlineKeyboardMarkup:
    """Send on its own row, below — a shared row «Cancel» and «Back»."""
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text=texts.BUTTON_SEND,
                    callback_data=ConfirmCb(action=ACTION_SEND).pack(),
                )
            ],
            [
                InlineKeyboardButton(
                    text=texts.BUTTON_CANCEL,
                    callback_data=BroadcastCtl(action=ACTION_CANCEL).pack(),
                ),
                InlineKeyboardButton(
                    text=texts.BUTTON_BACK,
                    callback_data=ConfirmCb(action=ACTION_BACK).pack(),
                ),
            ],
        ]
    )
