"""Tests for keyboards/menu.py: role-based reply keyboard contents."""

from aiogram.types import ReplyKeyboardMarkup

import texts
from keyboards.menu import menu_keyboard, role_keyboard
from services.members import ROLE_GROUP_LEAD, ROLE_SUPERVISOR, synthetic_member


def _button_texts(markup: ReplyKeyboardMarkup) -> list[str]:
    return [button.text for row in markup.keyboard for button in row]


def test_approved_student_without_roles_gets_absence_only():
    markup = role_keyboard(synthetic_member([]), is_admin=False)

    assert _button_texts(markup) == [texts.MENU_ABSENCE]


def test_group_lead_gets_absence_and_reports():
    markup = role_keyboard(synthetic_member([ROLE_GROUP_LEAD]), is_admin=False)

    assert _button_texts(markup) == [texts.MENU_ABSENCE, texts.MENU_REPORTS]


def test_supervisor_gets_reports_only():
    markup = role_keyboard(synthetic_member([ROLE_SUPERVISOR]), is_admin=False)

    assert _button_texts(markup) == [texts.MENU_REPORTS]


def test_admin_without_member_gets_both():
    markup = role_keyboard(None, is_admin=True)

    assert _button_texts(markup) == [texts.MENU_ABSENCE, texts.MENU_REPORTS]


def test_menu_keyboard_is_student_menu():
    assert _button_texts(menu_keyboard()) == [texts.MENU_ABSENCE]
