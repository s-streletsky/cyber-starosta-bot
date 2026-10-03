"""Entry point: logging → Bot → Dispatcher → middleware → errors → routers → polling."""

import asyncio
import logging
from typing import Awaitable, Callable

from aiogram import Bot, Dispatcher
from aiogram.fsm.storage.base import StorageKey
from aiogram.types import ErrorEvent, Update, User

import texts
from config import ADMIN_USER_IDS, BOT_TOKEN, DATA_DIR
from handlers.absence import router as absence_router
from handlers.admin import router as admin_router
from handlers.log_helpers import user_tag
from handlers.middleware import AccessControlMiddleware
from handlers.notify import notify_safe
from handlers.pending import router as pending_router
from handlers.reply_menu import menu_for
from handlers.report import router as report_router
from handlers.start import router as start_router
from keyboards.menu import menu_keyboard
from services.members import is_active_group_lead, is_admin
from storage import Storage, StorageCorruptError

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger(__name__)


def _fsm_key(update: Update, bot_id: int) -> StorageKey | None:
    """FSM state key to reset on error; None if there is no user."""
    if update.message:
        user = update.message.from_user
        chat_id: int | None = update.message.chat.id
    elif update.callback_query:
        user = update.callback_query.from_user
        callback_message = update.callback_query.message
        chat_id = callback_message.chat.id if callback_message else None
    else:
        return None

    if user is None:
        return None
    if chat_id is None:
        # Very old message: for a private chat chat_id == user_id.
        chat_id = user.id
    return StorageKey(bot_id=bot_id, chat_id=chat_id, user_id=user.id)


def _update_user(update: Update) -> User | None:
    """Update author (message or callback_query) or None if there is none."""
    if update.message:
        return update.message.from_user
    if update.callback_query:
        return update.callback_query.from_user
    return None


async def _warn_if_head_lead_inactive(storage: Storage) -> None:
    """Warn when the head-lead flag points at someone who is no longer an active group_lead."""
    head_lead_id = await storage.get_head_lead()
    if head_lead_id is None:
        return
    head_lead = await storage.get_member(head_lead_id)
    is_active = is_active_group_lead(head_lead)
    if not is_active:
        logger.warning(
            "head lead id=%s is not an active group_lead; cards fall back to admins",
            head_lead_id,
        )


def make_error_handler(
    bot: Bot, storage: Storage, dp: Dispatcher
) -> Callable[[ErrorEvent], Awaitable[None]]:
    """Builds the global error handler; alerts admins once on a corrupt roster."""
    storage_alert_sent = False

    async def on_error(event: ErrorEvent) -> None:
        nonlocal storage_alert_sent
        user = _update_user(event.update)
        if user is not None:
            tag = await user_tag(bot, storage, user.id, user)
            logger.error("Unhandled error in update: user %s", tag, exc_info=event.exception)
        else:
            logger.error("Unhandled error in update", exc_info=event.exception)

        if isinstance(event.exception, StorageCorruptError) and not storage_alert_sent:
            storage_alert_sent = True
            try:
                for admin_id in ADMIN_USER_IDS:
                    await notify_safe(
                        bot,
                        storage,
                        admin_id,
                        texts.ADMIN_STORAGE_ALERT,
                        context="storage corruption",
                    )
            except Exception:
                logger.warning("Failed to alert admins about storage corruption", exc_info=True)

        # The user must not be left in a dangling state.
        key = _fsm_key(event.update, bot.id)
        if key is not None:
            try:
                await dp.storage.set_state(key, state=None)
            except Exception:
                logger.warning("Failed to reset FSM state for %s", key, exc_info=True)

        update = event.update
        try:
            if update.callback_query:
                await update.callback_query.answer(texts.ERROR_REPLY, show_alert=True)
            elif update.message and update.message.from_user:
                user_id = update.message.from_user.id
                try:
                    keyboard = await menu_for(storage, user_id, is_admin(user_id))
                except Exception:
                    logger.warning("Failed to build role keyboard for error reply", exc_info=True)
                    keyboard = menu_keyboard()
                await update.message.answer(texts.ERROR_REPLY, reply_markup=keyboard)
        except Exception:
            logger.warning("Failed to notify user about error", exc_info=True)

    return on_error


async def main() -> None:
    bot = Bot(token=BOT_TOKEN)
    dp = Dispatcher()

    storage = Storage(DATA_DIR)
    dp.workflow_data["storage"] = storage
    logger.info("DATA_DIR=%s", DATA_DIR)
    await _warn_if_head_lead_inactive(storage)

    dp.update.outer_middleware(AccessControlMiddleware())
    dp.errors.register(make_error_handler(bot, storage, dp))

    # Order matters: the absence router holds the catch-all stale handler and goes last.
    dp.include_router(start_router)
    dp.include_router(pending_router)
    dp.include_router(admin_router)
    dp.include_router(report_router)
    dp.include_router(absence_router)

    await dp.start_polling(bot)


if __name__ == "__main__":
    asyncio.run(main())
