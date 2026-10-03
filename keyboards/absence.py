"""Inline keyboards for the "I will be absent" flow."""

from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup

import texts
from callbacks import (
    ACTION_BACK,
    ACTION_CANCEL,
    ACTION_NEXT,
    ACTION_SEND,
    ConfirmCb,
    DayCb,
    DayCtl,
    ReasonCb,
)
from services.absence import REASONS


def day_keyboard(days: list[dict], selected: set[str]) -> InlineKeyboardMarkup:
    """One day per row (✅ on selected), below — "Next" and "Cancel"."""
    rows: list[list[InlineKeyboardButton]] = []
    for entry in days:
        key = entry["day"].isoformat()
        marker = texts.DAY_MARKER_SELECTED if key in selected else texts.DAY_MARKER_UNSELECTED
        rows.append(
            [
                InlineKeyboardButton(
                    text=marker + entry["label"],
                    callback_data=DayCb(date=key).pack(),
                )
            ]
        )
    rows.append(
        [
            InlineKeyboardButton(
                text=texts.BUTTON_NEXT,
                callback_data=DayCtl(action=ACTION_NEXT).pack(),
            )
        ]
    )
    rows.append(
        [
            InlineKeyboardButton(
                text=texts.BUTTON_CANCEL,
                callback_data=DayCtl(action=ACTION_CANCEL).pack(),
            )
        ]
    )
    return InlineKeyboardMarkup(inline_keyboard=rows)


def reason_keyboard() -> InlineKeyboardMarkup:
    """Reasons 2 per row, below — a shared row "Back" and "Cancel"."""
    rows: list[list[InlineKeyboardButton]] = []
    for start in range(0, len(REASONS), 2):
        rows.append(
            [
                InlineKeyboardButton(
                    text=label,
                    callback_data=ReasonCb(code=code).pack(),
                )
                for code, label in REASONS[start : start + 2]
            ]
        )
    rows.append(
        [
            InlineKeyboardButton(
                text=texts.BUTTON_BACK,
                callback_data=ReasonCb(code=ACTION_BACK).pack(),
            ),
            InlineKeyboardButton(
                text=texts.BUTTON_CANCEL,
                callback_data=DayCtl(action=ACTION_CANCEL).pack(),
            ),
        ]
    )
    return InlineKeyboardMarkup(inline_keyboard=rows)


def confirm_keyboard(has_replaced: bool) -> InlineKeyboardMarkup:
    """Send-replace button if there are replacements, otherwise send."""
    send_text = texts.BUTTON_SEND_REPLACE if has_replaced else texts.BUTTON_SEND
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text=send_text,
                    callback_data=ConfirmCb(action=ACTION_SEND).pack(),
                )
            ],
            [
                InlineKeyboardButton(
                    text=texts.BUTTON_BACK,
                    callback_data=ConfirmCb(action=ACTION_BACK).pack(),
                )
            ],
            [
                InlineKeyboardButton(
                    text=texts.BUTTON_CANCEL,
                    callback_data=DayCtl(action=ACTION_CANCEL).pack(),
                )
            ],
        ]
    )


def back_keyboard() -> InlineKeyboardMarkup:
    """Only "Back" — for the "everything already marked" case."""
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text=texts.BUTTON_BACK,
                    callback_data=ConfirmCb(action=ACTION_BACK).pack(),
                )
            ]
        ]
    )
