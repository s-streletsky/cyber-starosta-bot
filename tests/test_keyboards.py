"""Tests for keyboards/menu.py: role-based reply keyboard contents."""

from aiogram.types import ReplyKeyboardMarkup

import texts
from keyboards.menu import menu_keyboard, role_keyboard
from services.members import ROLE_GROUP_LEAD, ROLE_SUPERVISOR, synthetic_member


def _rows(markup: ReplyKeyboardMarkup) -> list[list[str]]:
    return [[button.text for button in row] for row in markup.keyboard]


def test_approved_student_without_roles_gets_absence_only():
    markup = role_keyboard(synthetic_member([]), is_admin=False)

    assert _rows(markup) == [[texts.MENU_ABSENCE, texts.MENU_DELETE]]


def test_group_lead_gets_absence_and_reports():
    markup = role_keyboard(synthetic_member([ROLE_GROUP_LEAD]), is_admin=False)

    assert _rows(markup) == [
        [texts.MENU_ABSENCE, texts.MENU_DELETE],
        [texts.MENU_REPORTS],
        [texts.MENU_BROADCAST],
    ]


def test_supervisor_gets_reports_and_broadcast():
    markup = role_keyboard(synthetic_member([ROLE_SUPERVISOR]), is_admin=False)

    assert _rows(markup) == [
        [texts.MENU_REPORTS],
        [texts.MENU_BROADCAST],
    ]


def test_admin_without_member_gets_both():
    markup = role_keyboard(None, is_admin=True)

    assert _rows(markup) == [
        [texts.MENU_ABSENCE, texts.MENU_DELETE],
        [texts.MENU_REPORTS],
        [texts.MENU_BROADCAST],
    ]


def test_menu_keyboard_is_student_menu():
    assert _rows(menu_keyboard()) == [[texts.MENU_ABSENCE, texts.MENU_DELETE]]
