"""/start and onboarding: statuses, full name, request.

Logic by status:
- env admin: straight to the approved branch (profile name, edits manually in members.json);
- approved: greeting + role-based keyboard;
- pending: "already under review";
- removed: "Access closed" (can come back with a new request);
- new (no record): ask for the full name — strict "Surname Name".
"""

import logging

from aiogram import F, Router
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import Message

import texts
from handlers.log_helpers import user_tag
from handlers.pending import send_request_card
from keyboards.menu import role_keyboard
from services.members import is_admin, validate_full_name
from storage import MEMBER_APPROVED, MEMBER_PENDING, Storage

logger = logging.getLogger(__name__)
router = Router()


class OnboardingForm(StatesGroup):
    full_name = State()


def is_onboarding_state(raw_state: object) -> bool:
    """True only for the exact onboarding full-name state (used by the middleware)."""
    return raw_state == OnboardingForm.full_name.state


@router.message(Command("start"))
async def cmd_start(message: Message, state: FSMContext, storage: Storage) -> None:
    user = message.from_user
    if not user:
        return

    logger.info("Start: %s", await user_tag(message.bot, storage, user.id, user))

    if is_admin(user.id):
        await state.clear()
        await storage.upsert_member(user.id, user.full_name, user.username, status=MEMBER_APPROVED)
        await message.answer(
            f"{texts.brand_greeting(user.id)}\n\n{texts.START_IN_GROUP}",
            reply_markup=role_keyboard(None, is_admin=True),
        )
        return

    member = await storage.get_member(user.id)
    status = member["status"] if member else None

    if member is not None and status == MEMBER_APPROVED:
        await state.clear()
        await storage.upsert_member(user.id, user.full_name, user.username)
        await message.answer(
            f"{texts.brand_greeting(user.id)}\n\n{texts.START_IN_GROUP}",
            reply_markup=role_keyboard(member, is_admin=False),
        )
        return

    if member is not None and status == MEMBER_PENDING:
        await state.clear()
        await message.answer(texts.START_PENDING)
        return

    # No record or removed: a (re)submission starts with the full name.
    await state.set_state(OnboardingForm.full_name)
    await message.answer(texts.ONBOARDING_PROMPT)


@router.message(OnboardingForm.full_name, F.text)
async def receive_full_name(
    message: Message, state: FSMContext, storage: Storage
) -> None:
    """Full-name text: strict validation, then a pending request + card to the recipient."""
    user = message.from_user
    if not user:
        return

    try:
        full_name = validate_full_name(message.text or "")
    except ValueError:
        await message.answer(texts.ONBOARDING_PROMPT)
        return

    await state.clear()
    await storage.resubmit_member(user.id, full_name, user.username)
    member = await storage.get_member(user.id) or {}
    await message.answer(texts.START_REQUEST_SENT)
    await send_request_card(message.bot, storage, user.id, member)
