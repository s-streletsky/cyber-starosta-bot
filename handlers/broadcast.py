"""The broadcast notifications flow: recipients → message → confirmation → send."""

from typing import Any

from aiogram import F, Router
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import CallbackQuery, InlineKeyboardMarkup, Message

import texts
from callbacks import (
    ACTION_ALL,
    ACTION_BACK,
    ACTION_CANCEL,
    ACTION_CUSTOM,
    ACTION_NEXT,
    ACTION_SEND,
    BroadcastCtl,
    ConfirmCb,
    MessageCb,
    RecipientCb,
)
from handlers.notify import notify_many
from handlers.reply_menu import menu_for
from keyboards.broadcast import (
    broadcast_confirm_keyboard,
    message_keyboard,
    recipient_keyboard,
)
from services.broadcast import (
    BROADCAST_TEXT_MAX,
    format_confirm,
    format_result,
    is_valid_message,
    message_text,
    resolve_recipients,
    validate_broadcast_text,
)
from services.members import can_send_notifications
from services.members import is_admin as is_env_admin
from storage import MEMBER_APPROVED, Storage

router = Router()

# Menu buttons must fall through to their own handlers instead of being read as input.
_MENU_TEXTS = frozenset(
    {
        texts.MENU_ABSENCE,
        texts.MENU_DELETE,
        texts.MENU_REPORTS,
        texts.MENU_BROADCAST,
    }
)


class BroadcastForm(StatesGroup):
    recipients = State()
    message = State()
    custom_text = State()
    confirm = State()


def _selected_keys(state_data: dict[str, Any]) -> set[str]:
    """Selected recipient keys (str user_id) from the FSM «id → bool» map."""
    stored = state_data.get("recipients", {})
    return {key for key, value in stored.items() if value}


async def _recipients(storage: Storage, sender_id: int) -> list[tuple[int, dict[str, Any]]]:
    """Fresh approved recipients minus the sender."""
    members = await storage.list_members(status=MEMBER_APPROVED)
    return resolve_recipients(members, sender_id)


async def _picker_view(
    state: FSMContext, storage: Storage, sender_id: int
) -> tuple[str, InlineKeyboardMarkup]:
    """Recipient picker: the prompt with the selected count and the member rows."""
    recipients = await _recipients(storage, sender_id)
    selected = _selected_keys(await state.get_data())
    text = texts.BROADCAST_PROMPT.format(count=len(selected))
    return text, recipient_keyboard(recipients, selected)


async def _confirm_view(
    state: FSMContext, storage: Storage, sender_id: int
) -> tuple[str, InlineKeyboardMarkup]:
    """Confirmation step: the selected recipients and the chosen message."""
    recipients = await _recipients(storage, sender_id)
    data = await state.get_data()
    selected = _selected_keys(data)
    chosen = [(user_id, member) for user_id, member in recipients if str(user_id) in selected]
    message = data.get("message_text") or ""
    return format_confirm(chosen, message), broadcast_confirm_keyboard()


async def _render(callback: CallbackQuery, view: tuple[str, InlineKeyboardMarkup]) -> None:
    text, keyboard = view
    await callback.message.edit_text(text, reply_markup=keyboard)
    await callback.answer()


@router.message(F.text == texts.MENU_BROADCAST)
async def start_broadcast(message: Message, state: FSMContext, storage: Storage) -> None:
    """Reply menu button — restart the flow, the old selection is reset."""
    user = message.from_user
    if user is None:
        return

    member = await storage.get_member(user.id)
    admin = is_env_admin(user.id)
    if not can_send_notifications(member, is_admin=admin):
        await message.answer(
            texts.NOT_ALLOWED_BROADCAST,
            reply_markup=await menu_for(storage, user.id, admin),
        )
        return

    recipients = await _recipients(storage, user.id)
    if not recipients:
        await state.clear()
        await message.answer(
            texts.BROADCAST_EMPTY,
            reply_markup=await menu_for(storage, user.id, admin),
        )
        return

    await state.set_state(BroadcastForm.recipients)
    await state.set_data({"recipients": {}})
    await message.answer(
        texts.BROADCAST_PROMPT.format(count=0),
        reply_markup=recipient_keyboard(recipients, set()),
    )


@router.callback_query(BroadcastForm.recipients, RecipientCb.filter())
async def toggle_recipient(
    callback: CallbackQuery, state: FSMContext, storage: Storage, callback_data: RecipientCb
) -> None:
    """Recipient tap: ✅ toggles, the picker is redrawn."""
    data = await state.get_data()
    recipients = dict(data.get("recipients", {}))
    key = str(callback_data.user_id)
    recipients[key] = not recipients.get(key, False)
    await state.update_data(recipients=recipients)

    await _render(callback, await _picker_view(state, storage, callback.from_user.id))


@router.callback_query(BroadcastForm.recipients, BroadcastCtl.filter(F.action == ACTION_ALL))
async def select_all(callback: CallbackQuery, state: FSMContext, storage: Storage) -> None:
    """«Усім студентам»: select every visible recipient, or clear the selection.

    A tap replaces the selection map with all currently visible recipients
    (dropping any key no longer in the roster) unless every visible recipient
    is already selected, in which case it clears the selection.
    """
    recipients = await _recipients(storage, callback.from_user.id)
    selected = _selected_keys(await state.get_data())
    visible = {str(user_id) for user_id, _ in recipients}

    if visible and visible <= selected:
        updated: dict[str, bool] = {}
    else:
        updated = {str(user_id): True for user_id, _ in recipients}
    await state.update_data(recipients=updated)

    await _render(callback, await _picker_view(state, storage, callback.from_user.id))


@router.callback_query(BroadcastForm.recipients, BroadcastCtl.filter(F.action == ACTION_NEXT))
async def next_to_message(callback: CallbackQuery, state: FSMContext) -> None:
    """Next: cannot proceed without selected recipients."""
    if not _selected_keys(await state.get_data()):
        await callback.answer(texts.BROADCAST_NO_RECIPIENTS, show_alert=True)
        return

    await state.set_state(BroadcastForm.message)
    await _render(callback, (texts.BROADCAST_MSG_PROMPT, message_keyboard()))


@router.callback_query(BroadcastForm.message, MessageCb.filter())
async def choose_message(
    callback: CallbackQuery, state: FSMContext, storage: Storage, callback_data: MessageCb
) -> None:
    """Message step: back to recipients, own text → free text, otherwise confirmation."""
    if callback_data.code == ACTION_BACK:
        await state.set_state(BroadcastForm.recipients)
        await _render(callback, await _picker_view(state, storage, callback.from_user.id))
        return

    if callback_data.code == ACTION_CUSTOM:
        await state.set_state(BroadcastForm.custom_text)
        await callback.message.edit_text(
            texts.BROADCAST_CUSTOM_PROMPT.format(limit=BROADCAST_TEXT_MAX)
        )
        await callback.answer()
        return

    if not is_valid_message(callback_data.code):
        await callback.answer(texts.STALE_CALLBACK, show_alert=True)
        return

    await state.update_data(
        message_code=callback_data.code,
        message_text=message_text(callback_data.code),
    )
    await state.set_state(BroadcastForm.confirm)
    await _render(callback, await _confirm_view(state, storage, callback.from_user.id))


@router.message(
    BroadcastForm.custom_text,
    F.text,
    ~F.text.in_(_MENU_TEXTS),
)
async def receive_custom_text(message: Message, state: FSMContext, storage: Storage) -> None:
    """Any text → the broadcast message; empty or too-long text → re-prompt.

    Menu buttons are excluded so they fall through to their own handlers
    instead of being stored as the message text.
    """
    user = message.from_user
    if not user:
        return

    try:
        custom_text = validate_broadcast_text(message.text or "")
    except ValueError:
        if (message.text or "").strip():
            reply = texts.BROADCAST_CUSTOM_TOO_LONG.format(limit=BROADCAST_TEXT_MAX)
        else:
            reply = texts.BROADCAST_CUSTOM_EMPTY
        await message.answer(reply)
        return

    await state.update_data(message_code=ACTION_CUSTOM, message_text=custom_text)
    await state.set_state(BroadcastForm.confirm)
    text, keyboard = await _confirm_view(state, storage, user.id)
    await message.answer(text, reply_markup=keyboard)


@router.message(
    BroadcastForm.recipients,
    F.text,
    ~F.text.in_(_MENU_TEXTS),
)
async def recipients_text_hint(message: Message, state: FSMContext, storage: Storage) -> None:
    """Plain text at the recipient step: re-show the picker with a hint."""
    user = message.from_user
    if user is None:
        return
    text, keyboard = await _picker_view(state, storage, user.id)
    await message.answer(f"{texts.BROADCAST_PICK_HINT}\n\n{text}", reply_markup=keyboard)


@router.message(
    BroadcastForm.message,
    F.text,
    ~F.text.in_(_MENU_TEXTS),
)
async def message_text_hint(message: Message, state: FSMContext) -> None:
    """Plain text at the message step: re-show the picker with a hint."""
    user = message.from_user
    if user is None:
        return
    await message.answer(
        f"{texts.BROADCAST_MSG_HINT}\n\n{texts.BROADCAST_MSG_PROMPT}",
        reply_markup=message_keyboard(),
    )


@router.callback_query(BroadcastForm.confirm, ConfirmCb.filter(F.action == ACTION_BACK))
async def confirm_back(callback: CallbackQuery, state: FSMContext) -> None:
    """Back from confirmation — to the message step, the recipients are kept."""
    await state.set_state(BroadcastForm.message)
    await _render(callback, (texts.BROADCAST_MSG_PROMPT, message_keyboard()))


@router.callback_query(BroadcastForm.recipients, BroadcastCtl.filter(F.action == ACTION_CANCEL))
@router.callback_query(BroadcastForm.message, BroadcastCtl.filter(F.action == ACTION_CANCEL))
@router.callback_query(BroadcastForm.custom_text, BroadcastCtl.filter(F.action == ACTION_CANCEL))
@router.callback_query(BroadcastForm.confirm, BroadcastCtl.filter(F.action == ACTION_CANCEL))
async def cancel_flow(callback: CallbackQuery, state: FSMContext, storage: Storage) -> None:
    """Cancel: the state is reset, the menu returns to the chat."""
    await state.clear()
    await callback.answer()
    user_id = callback.from_user.id
    keyboard = await menu_for(storage, user_id, is_env_admin(user_id))
    if callback.message is not None and hasattr(callback.message, "answer"):
        await callback.message.answer(texts.CANCELLED, reply_markup=keyboard)


@router.callback_query(BroadcastForm.confirm, ConfirmCb.filter(F.action == ACTION_SEND))
async def confirm_send(callback: CallbackQuery, state: FSMContext, storage: Storage) -> None:
    """Send: the message goes to every selected recipient, then the result."""
    user_id = callback.from_user.id
    member = await storage.get_member(user_id)
    if not can_send_notifications(member, is_admin=is_env_admin(user_id)):
        await state.clear()
        await callback.answer(texts.NOT_ALLOWED_BROADCAST, show_alert=True)
        return

    data = await state.get_data()
    message = data.get("message_text") or ""
    if not message:
        await state.clear()
        await callback.answer(texts.STALE_CALLBACK, show_alert=True)
        return

    recipients = await _recipients(storage, user_id)
    visible = {str(recipient_id) for recipient_id, _ in recipients}
    selected = _selected_keys(data)
    # Reject stale selections: a card opened earlier may target members who
    # have since left the roster.
    if not selected or not selected <= visible:
        await state.clear()
        await callback.answer(texts.STALE_CALLBACK, show_alert=True)
        return

    recipient_ids = [
        recipient_id for recipient_id, _ in recipients if str(recipient_id) in selected
    ]

    # Clear before the network loop: a double-tap must not send twice.
    await state.clear()

    delivered, failed = await notify_many(
        callback.bot, storage, recipient_ids, message, context="broadcast"
    )
    keyboard = await menu_for(storage, user_id, is_env_admin(user_id))
    if callback.message is not None and hasattr(callback.message, "answer"):
        await callback.message.answer(
            format_result(delivered, failed), reply_markup=keyboard
        )
    await callback.answer()
