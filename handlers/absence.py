"""The "I will be absent" flow: days → reason → confirmation → storage write."""

from datetime import date, datetime
from typing import Any

from aiogram import F, Router
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import CallbackQuery, InlineKeyboardMarkup, Message

import texts
from callbacks import (
    ACTION_BACK,
    ACTION_CANCEL,
    ACTION_NEXT,
    ACTION_SEND,
    DELETE_CONFIRM,
    ConfirmCb,
    DayCb,
    DayCtl,
    DeleteCb,
    ReasonCb,
)
from config import TZ
from handlers.reply_menu import menu_for
from keyboards.absence import (
    back_keyboard,
    confirm_keyboard,
    day_keyboard,
    delete_confirm_keyboard,
    reason_keyboard,
)
from services.absence import (
    REASON_OTHER,
    REASON_TEXT_MAX,
    ReasonTextError,
    build_days,
    build_success_text,
    classify_record,
    format_confirm,
    format_dates_short,
    format_delete_confirm,
    format_delete_result,
    is_deletable_day,
    is_valid_reason,
    reason_display,
    validate_reason_text,
)
from services.members import can_mark_absence
from services.members import is_admin as is_env_admin
from storage import ABSENCE_DELETED, ABSENCE_IDENTICAL, ABSENCE_REPLACED, Storage

router = Router()


class AbsenceForm(StatesGroup):
    day = State()
    reason = State()
    other_text = State()
    confirm = State()
    delete_day = State()
    delete_confirm = State()


def current_day() -> date:
    """Today in the bot time zone (a seam for tests)."""
    return datetime.now(TZ).date()


def _selected_days(state_data: dict[str, Any]) -> list[date]:
    """Selected dates in ascending order (stored in FSM as «date → bool»)."""
    stored = state_data.get("days", {})
    return sorted(date.fromisoformat(key) for key, value in stored.items() if value)


def _visible_day_strings() -> set[str]:
    return {entry["day"].isoformat() for entry in build_days(TZ)}


async def _deletable_days(storage: Storage, user_id: int) -> list[dict[str, Any]]:
    """Current-window days that still have a live absence record for this user."""
    deletable: list[dict[str, Any]] = []
    for entry in build_days(TZ):
        record = await storage.get_record(user_id, entry["day"].isoformat())
        if record:
            deletable.append(entry)
    return deletable


async def _day_step_view(state: FSMContext) -> tuple[str, InlineKeyboardMarkup]:
    """Day step: only the 3 current days remain (previous window selection is dropped)."""
    data = await state.get_data()
    days = build_days(TZ)
    visible = _visible_day_strings()
    stored = {key: value for key, value in data.get("days", {}).items() if key in visible}
    await state.update_data(days=stored)

    selected = {key for key, value in stored.items() if value}
    text = texts.DAY_PROMPT.format(count=len(selected))
    return text, day_keyboard(days, selected)


async def _delete_step_view(
    state: FSMContext, storage: Storage, user_id: int
) -> tuple[str, InlineKeyboardMarkup]:
    """Delete picker: only the user's current records stay selectable."""
    data = await state.get_data()
    deletable = await _deletable_days(storage, user_id)
    visible = {entry["day"].isoformat() for entry in deletable}
    stored = {key: value for key, value in data.get("days", {}).items() if key in visible}
    await state.update_data(days=stored)

    selected = {key for key, value in stored.items() if value}
    text = texts.DELETE_PROMPT.format(count=len(selected))
    return text, day_keyboard(deletable, selected)


def _reason_step_view(dates: list[date]) -> tuple[str, InlineKeyboardMarkup]:
    text = texts.REASON_PROMPT.format(dates=format_dates_short(dates))
    return text, reason_keyboard()


async def _confirm_step_view(
    state: FSMContext, storage: Storage, user_id: int
) -> tuple[str, InlineKeyboardMarkup]:
    """Confirmation step: per-date summary and a send button."""
    data = await state.get_data()
    dates = _selected_days(data)
    reason_code = data.get("reason_code", "")
    reason_text = data.get("reason_text")

    # Existing records are needed both for the summary and the "Replace" button.
    existing: dict[str, dict[str, Any]] = {}
    for day in dates:
        key = day.isoformat()
        record = await storage.get_record(user_id, key)
        if record:
            existing[key] = record

    statuses = [
        classify_record(existing.get(day.isoformat()), reason_code, reason_text) for day in dates
    ]
    if all(status == ABSENCE_IDENTICAL for status in statuses):
        text = texts.ALL_IDENTICAL.format(
            dates=format_dates_short(dates),
            reason=reason_display(reason_code, reason_text),
        )
        return text, back_keyboard()

    summary = format_confirm(dates, reason_code, reason_text, existing)
    return f"{summary}\n{texts.CONFIRM_QUESTION}", confirm_keyboard(ABSENCE_REPLACED in statuses)


async def _render(callback: CallbackQuery, view: tuple[str, InlineKeyboardMarkup]) -> None:
    text, keyboard = view
    await callback.message.edit_text(text, reply_markup=keyboard)
    await callback.answer()


@router.message(F.text == texts.MENU_ABSENCE)
async def start_absence(message: Message, state: FSMContext, storage: Storage) -> None:
    """Reply menu button — restart the flow, the old selection is reset."""
    user = message.from_user
    if user is None:
        return

    member = await storage.get_member(user.id)
    admin = is_env_admin(user.id)
    if not can_mark_absence(member, is_admin=admin):
        await message.answer(
            texts.NOT_ALLOWED_ABSENCE,
            reply_markup=await menu_for(storage, user.id, admin),
        )
        return

    await state.set_state(AbsenceForm.day)
    await state.set_data({"days": {}})
    text, keyboard = await _day_step_view(state)
    await message.answer(text, reply_markup=keyboard)


@router.callback_query(AbsenceForm.day, DayCb.filter())
async def toggle_day(
    callback: CallbackQuery, state: FSMContext, callback_data: DayCb
) -> None:
    """Day tap: ✅ toggles, the message is redrawn."""
    data = await state.get_data()
    days = dict(data.get("days", {}))
    days[callback_data.date] = not days.get(callback_data.date, False)
    await state.update_data(days=days)

    await _render(callback, await _day_step_view(state))


@router.callback_query(AbsenceForm.day, DayCtl.filter(F.action == ACTION_NEXT))
async def next_to_reason(callback: CallbackQuery, state: FSMContext) -> None:
    """Next: cannot proceed without selected days."""
    dates = _selected_days(await state.get_data())
    if not dates:
        await callback.answer(texts.ALERT_PICK_DAY, show_alert=True)
        return

    await state.set_state(AbsenceForm.reason)
    await _render(callback, _reason_step_view(dates))


@router.callback_query(AbsenceForm.day, DayCtl.filter(F.action == ACTION_CANCEL))
@router.callback_query(AbsenceForm.reason, DayCtl.filter(F.action == ACTION_CANCEL))
@router.callback_query(AbsenceForm.confirm, DayCtl.filter(F.action == ACTION_CANCEL))
@router.callback_query(AbsenceForm.delete_day, DayCtl.filter(F.action == ACTION_CANCEL))
@router.callback_query(AbsenceForm.delete_confirm, DayCtl.filter(F.action == ACTION_CANCEL))
async def cancel_flow(callback: CallbackQuery, state: FSMContext, storage: Storage) -> None:
    """Cancel: the state is reset, the menu returns to the chat."""
    await state.clear()
    await callback.answer()
    user_id = callback.from_user.id
    keyboard = await menu_for(storage, user_id, is_env_admin(user_id))
    if callback.message is not None and hasattr(callback.message, "answer"):
        await callback.message.answer(texts.CANCELLED, reply_markup=keyboard)


@router.callback_query(AbsenceForm.reason, ReasonCb.filter())
async def choose_reason(
    callback: CallbackQuery,
    state: FSMContext,
    storage: Storage,
    callback_data: ReasonCb,
) -> None:
    """Reason step: back to days, "Other…" → free text, otherwise confirmation."""
    if callback_data.code == ACTION_BACK:
        await state.set_state(AbsenceForm.day)
        await _render(callback, await _day_step_view(state))
        return

    if callback_data.code == REASON_OTHER:
        await state.set_state(AbsenceForm.other_text)
        await callback.message.edit_text(texts.OTHER_TEXT_PROMPT.format(limit=REASON_TEXT_MAX))
        await callback.answer()
        return

    if not is_valid_reason(callback_data.code):
        await callback.answer(texts.STALE_CALLBACK, show_alert=True)
        return

    await state.update_data(reason_code=callback_data.code, reason_text=None)
    await state.set_state(AbsenceForm.confirm)
    await _render(callback, await _confirm_step_view(state, storage, callback.from_user.id))


@router.message(AbsenceForm.other_text, Command("cancel"))
async def cancel_other_text(message: Message, state: FSMContext, storage: Storage) -> None:
    """/cancel at the free-text step — reset."""
    user = message.from_user
    if user is None:
        return
    await state.clear()
    keyboard = await menu_for(storage, user.id, is_env_admin(user.id))
    await message.answer(texts.CANCELLED, reply_markup=keyboard)


@router.message(
    AbsenceForm.other_text,
    F.text,
    ~F.text.in_({texts.MENU_ABSENCE, texts.MENU_DELETE, texts.MENU_REPORTS}),
)
async def receive_other_text(message: Message, state: FSMContext, storage: Storage) -> None:
    """Any text → reason; empty or too-long text → re-prompt.

    Menu buttons are excluded so they fall through to their own handlers
    (start_absence / start_delete) instead of being stored as the reason.
    """
    user = message.from_user
    if not user:
        return

    try:
        reason_text = validate_reason_text(message.text or "")
    except ReasonTextError as exc:
        template = texts.OTHER_TEXT_TOO_LONG if exc.kind == "too_long" else texts.OTHER_TEXT_EMPTY
        text = template.format(limit=REASON_TEXT_MAX)
        keyboard = await menu_for(storage, user.id, is_env_admin(user.id))
        await message.answer(text, reply_markup=keyboard)
        return

    await state.update_data(reason_code=REASON_OTHER, reason_text=reason_text)
    await state.set_state(AbsenceForm.confirm)
    text, keyboard = await _confirm_step_view(state, storage, user.id)
    await message.answer(text, reply_markup=keyboard)


@router.callback_query(AbsenceForm.confirm, ConfirmCb.filter(F.action == ACTION_BACK))
async def confirm_back(callback: CallbackQuery, state: FSMContext) -> None:
    """Back from confirmation — to days, the selection is kept."""
    await state.set_state(AbsenceForm.day)
    await _render(callback, await _day_step_view(state))


@router.callback_query(AbsenceForm.confirm, ConfirmCb.filter(F.action == ACTION_SEND))
async def confirm_send(
    callback: CallbackQuery, state: FSMContext, storage: Storage
) -> None:
    """Send: one record per date, then the success step."""
    user_id = callback.from_user.id
    member = await storage.get_member(user_id)
    if not can_mark_absence(member, is_admin=is_env_admin(user_id)):
        await state.clear()
        await callback.answer(texts.NOT_ALLOWED_ABSENCE, show_alert=True)
        return

    data = await state.get_data()
    dates = _selected_days(data)
    # Reject stale selections: a card opened at 23:59 may submit a date
    # that has since left the current today..+2 window.
    visible = _visible_day_strings()
    if any(day.isoformat() not in visible for day in dates):
        await state.clear()
        await callback.answer(texts.STALE_CALLBACK, show_alert=True)
        return

    reason_code = data.get("reason_code")
    # `is_valid_reason` catches stale callbacks: FSM only reaches `confirm`
    # after valid days + reason are set, so `dates`/`reason_code` are guaranteed.
    if not is_valid_reason(reason_code):
        await callback.answer(texts.STALE_CALLBACK, show_alert=True)
        return

    reason_text = data.get("reason_text")
    await storage.upsert_absences_batch(
        user_id, [day.isoformat() for day in dates], reason_code, reason_text
    )

    success = build_success_text(dates, reason_display(reason_code, reason_text))
    keyboard = await menu_for(storage, user_id, is_env_admin(user_id))
    if callback.message is not None and hasattr(callback.message, "answer"):
        await callback.message.answer(success, reply_markup=keyboard)
    await callback.answer()
    await state.clear()


# --- logical deletion of the user's own absence records ---


@router.message(F.text == texts.MENU_DELETE)
async def start_delete(message: Message, state: FSMContext, storage: Storage) -> None:
    """Reply menu button — pick from the user's own existing records."""
    user = message.from_user
    if user is None:
        return

    member = await storage.get_member(user.id)
    admin = is_env_admin(user.id)
    if not can_mark_absence(member, is_admin=admin):
        await message.answer(
            texts.NOT_ALLOWED_ABSENCE,
            reply_markup=await menu_for(storage, user.id, admin),
        )
        return

    deletable = await _deletable_days(storage, user.id)
    if not deletable:
        await state.clear()
        await message.answer(
            texts.DELETE_NOTHING,
            reply_markup=await menu_for(storage, user.id, admin),
        )
        return

    await state.set_state(AbsenceForm.delete_day)
    await state.set_data({"days": {}})
    await message.answer(
        texts.DELETE_PROMPT.format(count=0),
        reply_markup=day_keyboard(deletable, set()),
    )


@router.callback_query(AbsenceForm.delete_day, DayCb.filter())
async def toggle_delete_day(
    callback: CallbackQuery, state: FSMContext, storage: Storage, callback_data: DayCb
) -> None:
    """Delete day tap: ✅ toggles; stale picks (whose record is gone) are pruned."""
    data = await state.get_data()
    days = dict(data.get("days", {}))
    days[callback_data.date] = not days.get(callback_data.date, False)
    await state.update_data(days=days)

    await _render(callback, await _delete_step_view(state, storage, callback.from_user.id))


@router.callback_query(AbsenceForm.delete_day, DayCtl.filter(F.action == ACTION_NEXT))
async def delete_next_to_confirm(callback: CallbackQuery, state: FSMContext) -> None:
    """Next: cannot proceed without chosen records; then show the confirmation."""
    dates = _selected_days(await state.get_data())
    if not dates:
        await callback.answer(texts.ALERT_PICK_DELETE, show_alert=True)
        return

    await state.set_state(AbsenceForm.delete_confirm)
    await _render(callback, (format_delete_confirm(dates), delete_confirm_keyboard()))


@router.callback_query(AbsenceForm.delete_confirm, DeleteCb.filter(F.action == ACTION_BACK))
async def delete_back(callback: CallbackQuery, state: FSMContext, storage: Storage) -> None:
    """Back from the delete confirmation — to the picker, the selection is kept."""
    await state.set_state(AbsenceForm.delete_day)
    await _render(callback, await _delete_step_view(state, storage, callback.from_user.id))


@router.callback_query(AbsenceForm.delete_confirm, DeleteCb.filter(F.action == DELETE_CONFIRM))
async def confirm_delete(
    callback: CallbackQuery, state: FSMContext, storage: Storage
) -> None:
    """Confirm: tombstone the chosen records, then report the outcome."""
    user_id = callback.from_user.id
    member = await storage.get_member(user_id)
    if not can_mark_absence(member, is_admin=is_env_admin(user_id)):
        await state.clear()
        await callback.answer(texts.NOT_ALLOWED_ABSENCE, show_alert=True)
        return

    selected = _selected_days(await state.get_data())
    today = current_day()
    if any(not is_deletable_day(day, today) for day in selected):
        await state.clear()
        await callback.answer(texts.DELETE_PAST_REJECTED, show_alert=True)
        return

    # A card opened at 23:59 may target dates that have since left the window.
    visible = _visible_day_strings()
    if any(day.isoformat() not in visible for day in selected):
        await state.clear()
        await callback.answer(texts.STALE_CALLBACK, show_alert=True)
        return

    results = await storage.delete_absences_batch(
        user_id, [day.isoformat() for day in selected]
    )
    deleted = [day for day, result in zip(selected, results) if result == ABSENCE_DELETED]
    keyboard = await menu_for(storage, user_id, is_env_admin(user_id))
    if callback.message is not None and hasattr(callback.message, "answer"):
        await callback.message.answer(format_delete_result(deleted), reply_markup=keyboard)
    await callback.answer()
    await state.clear()


# Must be last: any callback not matching the current FSM state.
@router.callback_query()
async def stale_callback(callback: CallbackQuery) -> None:
    await callback.answer(texts.STALE_CALLBACK, show_alert=True)
