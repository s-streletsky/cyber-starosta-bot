"""The "Selections" reports: the menu and the "today" absentee report."""

from datetime import date, datetime

from aiogram import F, Router
from aiogram.types import CallbackQuery, Message

import texts
from callbacks import ReportCb
from config import TZ
from keyboards.report import report_menu_keyboard
from services.absence import build_absentees, format_absentee_report
from services.members import can_view_reports, is_admin
from services.text import split_message
from storage import MEMBER_APPROVED, Storage

router = Router()

TELEGRAM_TEXT_MAX = 4096


def current_day() -> date:
    """Today in the bot time zone (a seam for tests)."""
    return datetime.now(TZ).date()


@router.message(F.text == texts.MENU_REPORTS)
async def open_reports(message: Message, storage: Storage) -> None:
    """Reply menu button: show the report menu to users allowed to view reports."""
    user = message.from_user
    if user is None:
        return
    member = await storage.get_member(user.id)
    if not can_view_reports(member, is_admin=is_admin(user.id)):
        await message.answer(texts.NOT_ALLOWED_REPORTS)
        return
    await message.answer(texts.REPORT_PROMPT, reply_markup=report_menu_keyboard())


@router.callback_query(ReportCb.filter())
async def show_today_report(callback: CallbackQuery, storage: Storage) -> None:
    """«rep:today»: edit the message into the list of today's absentees."""
    member = await storage.get_member(callback.from_user.id)
    if not can_view_reports(member, is_admin=is_admin(callback.from_user.id)):
        await callback.answer(texts.NOT_ALLOWED_REPORTS, show_alert=True)
        return

    day = current_day()
    members = await storage.list_members(status=MEMBER_APPROVED)
    records = await storage.list_absences_for_date(day.isoformat())
    absentees = build_absentees(members, records)
    text = format_absentee_report(day, absentees)
    chunks = split_message(text, TELEGRAM_TEXT_MAX)
    if callback.message is not None and hasattr(callback.message, "edit_text"):
        await callback.message.edit_text(chunks[0])
        if hasattr(callback.message, "answer"):
            for extra in chunks[1:]:
                await callback.message.answer(extra)
    await callback.answer()
