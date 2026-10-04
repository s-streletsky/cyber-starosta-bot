"""Join requests: cards, /pending, approval and rejection.

The card goes to the head group lead (the member with `is_head_lead`), and if none is
assigned/unavailable — to all env admins. Any group_lead and admin can process
the queue: /pending shows the same cards.
"""

import logging
from typing import Any

from aiogram import Router
from aiogram.exceptions import TelegramBadRequest
from aiogram.filters import Command
from aiogram.types import CallbackQuery, Message

import texts
from callbacks import APPROVE_ACCEPT, APPROVE_REJECT, ApproveCb
from config import ADMIN_USER_IDS
from handlers.log_helpers import user_tag
from handlers.notify import notify_safe
from keyboards.approvals import request_keyboard
from keyboards.menu import role_keyboard
from services.members import can_process_requests, is_active_group_lead, is_admin
from storage import MEMBER_PENDING, RESULT_APPROVED, RESULT_REJECTED, Storage

logger = logging.getLogger(__name__)
router = Router()


def _identity(member: dict | None) -> tuple[str, str]:
    """(display_name, username) with the same fallbacks used on the request card."""
    if member is None:
        return "?", texts.NO_USERNAME
    return member.get("display_name", "?"), member.get("username") or texts.NO_USERNAME


def card_text(member: dict, user_id: int) -> str:
    display_name, username = _identity(member)
    return texts.REQUEST_CARD.format(
        display_name=display_name,
        username=username,
        user_id=user_id,
    )


async def _receiver_ids(storage: Storage) -> list[int]:
    """Head group lead if they are an active group_lead; otherwise env admins."""
    head_lead_id = await storage.get_head_lead()
    if head_lead_id is not None:
        member = await storage.get_member(head_lead_id)
        if is_active_group_lead(member):
            return [head_lead_id]
    return list(ADMIN_USER_IDS)


async def send_request_card(
    bot: Any, storage: Storage, user_id: int, member: dict
) -> None:
    """Sends the request card to the recipient (head lead → fallback admins)."""
    receivers = await _receiver_ids(storage)
    if not receivers:
        logger.warning(
            "Request %s was not delivered: no recipients (lead and admins are empty)",
            await user_tag(bot, storage, user_id),
        )
        return
    for receiver_id in receivers:
        try:
            await bot.send_message(
                receiver_id,
                card_text(member, user_id),
                reply_markup=request_keyboard(user_id),
            )
        except Exception:
            sender_tag = await user_tag(bot, storage, user_id)
            receiver_tag = await user_tag(bot, storage, receiver_id)
            logger.warning(
                "Failed to deliver request card %s to recipient %s",
                sender_tag,
                receiver_tag,
                exc_info=True,
            )


async def _is_manager(storage: Storage, user_id: int) -> bool:
    if is_admin(user_id):
        return True
    return can_process_requests(await storage.get_member(user_id), False)


@router.message(Command("pending"))
async def cmd_pending(message: Message, storage: Storage) -> None:
    """List of requests: cards with buttons. Only group_lead and admins."""
    user = message.from_user
    if not user or not await _is_manager(storage, user.id):
        await message.answer(texts.NOT_A_MANAGER)
        return

    pending = await storage.list_members(status=MEMBER_PENDING)
    if not pending:
        await message.answer(texts.PENDING_EMPTY)
        return

    for member_user_id, member in pending:
        await message.answer(
            card_text(member, member_user_id),
            reply_markup=request_keyboard(member_user_id),
        )


@router.callback_query(ApproveCb.filter())
async def handle_request(
    callback: CallbackQuery, storage: Storage, callback_data: ApproveCb
) -> None:
    """Card tap: accept or reject the request exactly once."""
    user = callback.from_user
    if not user or not await _is_manager(storage, user.id):
        await callback.answer(texts.NOT_A_MANAGER, show_alert=True)
        return

    if callback_data.action not in (APPROVE_ACCEPT, APPROVE_REJECT):
        await callback.answer(texts.STALE_CARD, show_alert=True)
        return

    member = await storage.get_member(callback_data.user_id)
    display_name, username = _identity(member)

    is_accept = callback_data.action == APPROVE_ACCEPT
    if is_accept:
        result = await storage.approve_pending(callback_data.user_id)
        if result != RESULT_APPROVED:
            await callback.answer(texts.STALE_CARD, show_alert=True)
            return
        verdict = texts.CARD_APPROVED.format(
            display_name=display_name, username=username, user_id=callback_data.user_id
        )
    else:
        result = await storage.reject_pending(callback_data.user_id)
        if result != RESULT_REJECTED:
            await callback.answer(texts.STALE_CARD, show_alert=True)
            return
        verdict = texts.CARD_REJECTED.format(
            display_name=display_name, username=username, user_id=callback_data.user_id
        )

    # Ack right after the transition: the click is done, the remaining network
    # calls (user notification, card edit) must not delay the button spinner.
    await callback.answer()

    if is_accept:
        # The keyboard must reflect the post-approval status: the pre-transition
        # snapshot is still "pending" and yields an empty reply menu.
        approved_member = await storage.get_member(callback_data.user_id)
        await _notify_approved(
            callback.bot, storage, callback_data.user_id, approved_member or {}
        )

    if callback.message is not None and hasattr(callback.message, "edit_text"):
        try:
            await callback.message.edit_text(verdict)
        except TelegramBadRequest as exc:
            if "message is not modified" not in str(exc):
                raise


async def _notify_approved(
    bot: Any, storage: Storage, user_id: int, member: dict
) -> None:
    """Tell the approved user; a delivery failure must not break the card."""
    await notify_safe(
        bot,
        storage,
        user_id,
        texts.APPROVED_NOTIFY,
        reply_markup=role_keyboard(member, is_admin=False),
        context="approval",
    )
