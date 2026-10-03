"""Inline keyboard for join-request cards: accept / reject."""

from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup

import texts
from callbacks import APPROVE_ACCEPT, APPROVE_REJECT, ApproveCb


def request_keyboard(user_id: int) -> InlineKeyboardMarkup:
    """One row with the accept and reject buttons for a single request card."""
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text=texts.BUTTON_ACCEPT,
                    callback_data=ApproveCb(action=APPROVE_ACCEPT, user_id=user_id).pack(),
                ),
                InlineKeyboardButton(
                    text=texts.BUTTON_REJECT,
                    callback_data=ApproveCb(action=APPROVE_REJECT, user_id=user_id).pack(),
                ),
            ]
        ]
    )
