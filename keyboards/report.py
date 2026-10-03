"""Inline keyboard for the "Selections" report menu."""

from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup

import texts
from callbacks import REPORT_TODAY, ReportCb


def report_menu_keyboard() -> InlineKeyboardMarkup:
    """Inline report menu: a single "today" button."""
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text=texts.REPORT_TODAY_BUTTON,
                    callback_data=ReportCb(action=REPORT_TODAY).pack(),
                )
            ]
        ]
    )
