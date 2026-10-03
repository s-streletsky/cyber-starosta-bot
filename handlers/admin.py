"""Admin commands (env admins only): /promote /demote /remove /sethead.

All interactive: a command without arguments shows a list of buttons, a tap
performs the action. Nobody remembers student IDs — they do not need to be entered.
"""

import logging

from aiogram import Router
from aiogram.filters import Command
from aiogram.types import CallbackQuery, Message, ReplyKeyboardRemove

import texts
from callbacks import (
    ADMIN_DEMOTE,
    ADMIN_PICK_PROMOTE,
    ADMIN_REMOVE,
    ADMIN_SET_HEAD,
    ADMIN_SET_ROLE,
    AdminCb,
)
from handlers.notify import notify_safe
from keyboards.admin import person_list_keyboard, role_choice_keyboard
from keyboards.menu import role_keyboard
from services.members import (
    has_any_role,
    has_role,
    is_admin,
    is_approved,
    is_valid_role,
    member_label,
    role_name,
    synthetic_member,
)
from storage import MEMBER_APPROVED, ROLE_GROUP_LEAD, Storage

logger = logging.getLogger(__name__)
router = Router()


async def _require_admin(message: Message) -> bool:
    if is_admin(message.from_user.id if message.from_user else None):
        return True
    await message.answer(texts.ADMIN_ONLY)
    return False


async def _stale(callback: CallbackQuery) -> None:
    await callback.answer(texts.STALE_CARD, show_alert=True)


async def _approved_non_admins(storage: Storage) -> list[tuple[int, dict]]:
    return [
        (user_id, member)
        for user_id, member in await storage.list_members(status=MEMBER_APPROVED)
        if not is_admin(user_id)
    ]


@router.message(Command("promote"))
async def cmd_promote(message: Message, storage: Storage) -> None:
    if not await _require_admin(message):
        return
    candidates = [pair for pair in await _approved_non_admins(storage) if not has_any_role(pair[1])]
    if not candidates:
        await message.answer(texts.PROMOTE_EMPTY)
        return
    keyboard = person_list_keyboard(candidates, ADMIN_PICK_PROMOTE)
    await message.answer(texts.PROMOTE_PROMPT, reply_markup=keyboard)


@router.message(Command("demote"))
async def cmd_demote(message: Message, storage: Storage) -> None:
    if not await _require_admin(message):
        return
    with_roles = [pair for pair in await _approved_non_admins(storage) if has_any_role(pair[1])]
    if not with_roles:
        await message.answer(texts.DEMOTE_EMPTY)
        return
    keyboard = person_list_keyboard(with_roles, ADMIN_DEMOTE)
    await message.answer(texts.DEMOTE_PROMPT, reply_markup=keyboard)


@router.message(Command("remove"))
async def cmd_remove(message: Message, storage: Storage) -> None:
    if not await _require_admin(message):
        return
    removable = await _approved_non_admins(storage)
    if not removable:
        await message.answer(texts.REMOVE_EMPTY)
        return
    head_lead_id = await storage.get_head_lead()
    keyboard = person_list_keyboard(removable, ADMIN_REMOVE, head_lead_id=head_lead_id)
    await message.answer(texts.REMOVE_PROMPT, reply_markup=keyboard)


@router.message(Command("sethead"))
async def cmd_sethead(message: Message, storage: Storage) -> None:
    if not await _require_admin(message):
        return
    leads = await storage.list_members(status=MEMBER_APPROVED, role=ROLE_GROUP_LEAD)
    if not leads:
        await message.answer(texts.HEAD_LEAD_EMPTY)
        return
    head_lead_id = await storage.get_head_lead()
    await message.answer(
        texts.HEAD_LEAD_PROMPT,
        reply_markup=person_list_keyboard(leads, ADMIN_SET_HEAD, head_lead_id=head_lead_id),
    )


@router.callback_query(AdminCb.filter())
async def handle_admin_callback(
    callback: CallbackQuery, storage: Storage, callback_data: AdminCb
) -> None:
    """Tap on an admin list: rights and freshness are checked on the spot."""
    if not is_admin(callback.from_user.id if callback.from_user else None):
        await callback.answer(texts.ACCESS_DENIED, show_alert=True)
        return

    if callback.message is None:
        await callback.answer()
        return

    user_id = callback_data.user_id
    if is_admin(user_id):
        await _stale(callback)
        return
    member = await storage.get_member(user_id)

    if callback_data.action == ADMIN_PICK_PROMOTE:
        if not is_approved(member) or has_any_role(member):
            await _stale(callback)
            return
        await callback.message.edit_text(
            texts.ROLE_CHOICE_PROMPT.format(name=member_label(member)),
            reply_markup=role_choice_keyboard(user_id),
        )
        await callback.answer()
        return

    if callback_data.action == ADMIN_SET_ROLE:
        if not is_approved(member) or has_any_role(member):
            await _stale(callback)
            return
        role = callback_data.role
        if not is_valid_role(role):
            await _stale(callback)
            return
        await storage.add_role(user_id, role)
        await _notify_role_change(callback.bot, storage, user_id, role)
        await callback.message.edit_text(
            texts.PROMOTE_DONE.format(name=member_label(member), role=role_name(role))
        )
        await callback.answer()
        return

    if callback_data.action == ADMIN_DEMOTE:
        if not is_approved(member) or not has_any_role(member):
            await _stale(callback)
            return
        for role in list(member["roles"]):
            await storage.remove_role(user_id, role)
        if await storage.get_head_lead() == user_id:
            await storage.set_head_lead(None)
            await callback.message.edit_text(
                texts.DEMOTE_DONE.format(name=member_label(member))
                + "\n"
                + texts.HEAD_LEAD_CLEARED
            )
        else:
            await callback.message.edit_text(
                texts.DEMOTE_DONE.format(name=member_label(member))
            )
        await _notify_role_change(callback.bot, storage, user_id, None)
        await callback.answer()
        return

    if callback_data.action == ADMIN_REMOVE:
        if not is_approved(member):
            await _stale(callback)
            return
        head_lead_id = await storage.get_head_lead()
        was_head_lead = head_lead_id == user_id
        await storage.remove_member(user_id)
        await notify_safe(
            callback.bot,
            storage,
            user_id,
            texts.ACCESS_CLOSED_NOTIFY,
            reply_markup=ReplyKeyboardRemove(),
            context="removal",
        )
        verdict = texts.REMOVE_DONE.format(name=member_label(member))
        if was_head_lead:
            verdict = f"{verdict}\n{texts.HEAD_LEAD_CLEARED}"
        await callback.message.edit_text(verdict)
        await callback.answer()
        return

    if callback_data.action == ADMIN_SET_HEAD:
        if not is_approved(member) or not has_role(member, ROLE_GROUP_LEAD):
            await _stale(callback)
            return
        current = await storage.get_head_lead()
        if current == user_id:
            await storage.set_head_lead(None)
            await callback.message.edit_text(texts.HEAD_LEAD_CLEARED)
        else:
            await storage.set_head_lead(user_id)
            await callback.message.edit_text(
                texts.HEAD_LEAD_SET.format(name=member_label(member))
            )
        await callback.answer()
        return

    await callback.answer()


async def _notify_role_change(bot, storage: Storage, user_id: int, role: str | None) -> None:
    """Send the user a role change message and a keyboard for the new role."""
    if role is None:
        text = texts.ROLE_BACK_TO_STUDENT
        keyboard = role_keyboard(synthetic_member([]), is_admin=False)
    else:
        text = texts.ROLE_UPDATE_NOTIFY.format(role=role_name(role))
        keyboard = role_keyboard(synthetic_member([role]), is_admin=False)
    await notify_safe(bot, storage, user_id, text, reply_markup=keyboard, context="role change")
