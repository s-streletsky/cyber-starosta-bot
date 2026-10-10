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
    - can_view_reports and can_send_notifications → one management row,
      ordered «Сповіщення» then «Вибірки».

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
    management: list[KeyboardButton] = []
    if show_notifications:
        management.append(KeyboardButton(text=texts.MENU_BROADCAST))
    if show_reports:
        management.append(KeyboardButton(text=texts.MENU_REPORTS))
    if management:
        rows.append(management)
    return ReplyKeyboardMarkup(
        keyboard=rows,
        resize_keyboard=True,
        is_persistent=True,
    )


def menu_keyboard() -> ReplyKeyboardMarkup:
    """Student menu (fallback for paths with no roster access)."""
    return role_keyboard(synthetic_member([]), is_admin=False)
