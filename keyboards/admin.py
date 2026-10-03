"""Inline keyboards for admin flows: people lists and the role choice."""

from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup

import texts
from callbacks import ADMIN_SET_ROLE, AdminAction, AdminCb
from services.members import member_label
from storage import ROLE_GROUP_LEAD, ROLE_SUPERVISOR

_LIST_COLUMNS = 2


def person_list_keyboard(
    people: list[tuple[int, dict]], action: AdminAction, head_lead_id: int | None = None
) -> InlineKeyboardMarkup:
    """List of people in 2 columns; the head lead is marked with a crown."""
    rows: list[list[InlineKeyboardButton]] = []
    row: list[InlineKeyboardButton] = []
    for user_id, member in people:
        label = member_label(member)
        if head_lead_id is not None and user_id == head_lead_id:
            label = f"{texts.HEAD_LEAD_CROWN}{label}"
        row.append(
            InlineKeyboardButton(
                text=label,
                callback_data=AdminCb(action=action, user_id=user_id).pack(),
            )
        )
        if len(row) == _LIST_COLUMNS:
            rows.append(row)
            row = []
    if row:
        rows.append(row)
    return InlineKeyboardMarkup(inline_keyboard=rows)


def role_choice_keyboard(user_id: int) -> InlineKeyboardMarkup:
    """Two buttons: pick which role to grant to the user."""
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text=texts.BUTTON_ROLE_GROUP_LEAD,
                    callback_data=AdminCb(
                        action=ADMIN_SET_ROLE, user_id=user_id, role=ROLE_GROUP_LEAD
                    ).pack(),
                )
            ],
            [
                InlineKeyboardButton(
                    text=texts.BUTTON_ROLE_SUPERVISOR,
                    callback_data=AdminCb(
                        action=ADMIN_SET_ROLE, user_id=user_id, role=ROLE_SUPERVISOR
                    ).pack(),
                )
            ],
        ]
    )
