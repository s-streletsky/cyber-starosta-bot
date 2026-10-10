"""Reply keyboards by role: student, group_lead, supervisor."""

from aiogram.types import KeyboardButton, ReplyKeyboardMarkup

import texts
from services.members import (
    can_mark_absence,
    can_send_notifications,
    can_view_reports,
    synthetic_member,
)


def role_keyboard(member: dict | None, is_admin: bool) -> ReplyKeyboardMarkup:
    """Menu by rights:

    - can_mark_absence → [I will be absent, Delete an entry] share one row;
    - can_view_reports → [Selections] on its own row;
    - can_send_notifications → [Notifications] on its own row.

    Rights come from services.members, so this module never hard-codes role names.
    """
    show_absence = can_mark_absence(member, is_admin)
    show_reports = can_view_reports(member, is_admin)
    show_notifications = can_send_notifications(member, is_admin)

    rows: list[list[KeyboardButton]] = []
    if show_absence:
        rows.append(
            [
                KeyboardButton(text=texts.MENU_ABSENCE),
                KeyboardButton(text=texts.MENU_DELETE),
            ]
        )
    if show_reports:
        rows.append([KeyboardButton(text=texts.MENU_REPORTS)])
    if show_notifications:
        rows.append([KeyboardButton(text=texts.MENU_BROADCAST)])
    return ReplyKeyboardMarkup(
        keyboard=rows,
        resize_keyboard=True,
        is_persistent=True,
    )


def menu_keyboard() -> ReplyKeyboardMarkup:
    """Student menu (fallback for paths with no roster access)."""
    return role_keyboard(synthetic_member([]), is_admin=False)
