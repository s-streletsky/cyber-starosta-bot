"""Full real-Dispatcher integration tests: middleware + routers + error handler.

Unlike the unit tests, these drive real aiogram Update objects through a real
Dispatcher, with a fake BaseSession standing in for the Telegram HTTP layer.
"""

from datetime import UTC, date, datetime

import pytest
from aiogram import Bot, Dispatcher, Router
from aiogram.client.session.base import BaseSession
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.methods import AnswerCallbackQuery, EditMessageText, SendMessage
from aiogram.types import CallbackQuery, Chat, Message, Update, User

import texts
from bot import make_error_handler
from handlers.absence import router as absence_router
from handlers.admin import router as admin_router
from handlers.middleware import AccessControlMiddleware
from handlers.pending import router as pending_router
from handlers.report import router as report_router
from handlers.start import router as start_router
from storage import MEMBER_APPROVED, Storage, StorageCorruptError
from tests.fakes import ADMIN_ID


class _FakeSession(BaseSession):
    """Records outgoing Telegram calls and answers them with minimal objects."""

    def __init__(self) -> None:
        super().__init__()
        self.sent_messages: list[tuple[int, str]] = []
        self.edited_messages: list[tuple[int, str]] = []
        self.answered_callbacks: list[tuple[str, bool]] = []

    async def close(self) -> None:
        pass

    async def stream_content(self, url, headers=None, timeout=30, chunk_size=65536, **kwargs):
        yield b""

    async def make_request(self, bot, method, timeout=None):
        if isinstance(method, SendMessage):
            self.sent_messages.append((method.chat_id, method.text))
            return Message(
                message_id=len(self.sent_messages),
                date=datetime.now(UTC),
                chat=Chat(id=method.chat_id, type="private"),
                text=method.text,
            )
        if isinstance(method, AnswerCallbackQuery):
            self.answered_callbacks.append((method.text or "", bool(method.show_alert)))
            return True
        if isinstance(method, EditMessageText):
            self.edited_messages.append((method.chat_id, method.text))
            return Message(
                message_id=len(self.edited_messages),
                date=datetime.now(UTC),
                chat=Chat(id=method.chat_id, type="private"),
                text=method.text,
            )
        if method.__class__.__name__ == "GetChat":
            return Chat(id=method.chat_id, type="private", username=None)
        return True


@pytest.fixture(scope="module")
def dp() -> Dispatcher:
    """One real Dispatcher with the production routers in production order."""
    dispatcher = Dispatcher()
    dispatcher.update.outer_middleware(AccessControlMiddleware())
    dispatcher.include_router(start_router)
    dispatcher.include_router(pending_router)
    dispatcher.include_router(admin_router)
    dispatcher.include_router(report_router)
    dispatcher.include_router(absence_router)
    return dispatcher


@pytest.fixture(autouse=True)
def _fresh_fsm(dp: Dispatcher) -> None:
    # Routers can attach only once, so the Dispatcher is shared; reset FSM state
    # between tests to keep them independent.
    dp.fsm.storage = MemoryStorage()


def _user(user_id: int, username: str | None = "tester") -> User:
    return User(id=user_id, is_bot=False, first_name="Test", username=username)


def _message_update(update_id: int, text: str, user: User) -> Update:
    message = Message(
        message_id=update_id,
        date=datetime.now(UTC),
        chat=Chat(id=user.id, type="private"),
        from_user=user,
        text=text,
    )
    return Update(update_id=update_id, message=message)


def _callback_update(update_id: int, data: str, user: User) -> Update:
    message = Message(
        message_id=update_id,
        date=datetime.now(UTC),
        chat=Chat(id=user.id, type="private"),
        text="card",
    )
    callback = CallbackQuery(
        id=str(update_id),
        from_user=user,
        chat_instance=str(user.id),
        data=data,
        message=message,
    )
    return Update(update_id=update_id, callback_query=callback)


def _make_bot(dp: Dispatcher, storage: Storage, session: _FakeSession) -> Bot:
    dp.workflow_data["storage"] = storage
    return Bot(token="123456:TESTTOKEN", session=session)


async def test_start_unknown_user_sends_onboarding_prompt(dp, tmp_path):
    session = _FakeSession()
    bot = _make_bot(dp, Storage(tmp_path), session)

    await dp.feed_update(bot, _message_update(1, "/start", _user(111)))

    assert (111, texts.ONBOARDING_PROMPT) in session.sent_messages


async def test_onboarding_name_reaches_request_card(dp, tmp_path):
    session = _FakeSession()
    storage = Storage(tmp_path)
    bot = _make_bot(dp, storage, session)

    await dp.feed_update(bot, _message_update(1, "/start", _user(111)))
    await dp.feed_update(bot, _message_update(2, "Тестовий Студент", _user(111)))

    assert (111, texts.START_REQUEST_SENT) in session.sent_messages
    assert any(chat_id == ADMIN_ID for chat_id, _ in session.sent_messages)
    member = await storage.get_member(111)
    assert member is not None


async def test_approved_member_start_is_allowed_and_answered(dp, tmp_path):
    session = _FakeSession()
    storage = Storage(tmp_path)
    await storage.upsert_member(111, "Студент Тестовий", "student", status=MEMBER_APPROVED)
    bot = _make_bot(dp, storage, session)

    await dp.feed_update(bot, _message_update(1, "/start", _user(111)))

    assert any(texts.START_IN_GROUP in text for _, text in session.sent_messages)


async def test_denied_callback_answers_access_denied(dp, tmp_path):
    session = _FakeSession()
    bot = _make_bot(dp, Storage(tmp_path), session)

    await dp.feed_update(bot, _callback_update(1, "c:send", _user(111)))

    assert (texts.ACCESS_DENIED, True) in session.answered_callbacks


async def test_storage_corrupt_error_alerts_admins_and_user(dp, tmp_path):
    session = _FakeSession()
    storage = Storage(tmp_path)
    temp_router = Router()

    @temp_router.message()
    async def _boom(message: Message) -> None:
        raise StorageCorruptError("members.json is corrupt")

    dp.include_router(temp_router)
    bot = _make_bot(dp, storage, session)
    dp.errors.register(make_error_handler(bot, storage, dp))

    await dp.feed_update(bot, _message_update(1, "boom", _user(ADMIN_ID)))

    assert (ADMIN_ID, texts.ADMIN_STORAGE_ALERT) in session.sent_messages
    assert (ADMIN_ID, texts.ERROR_REPLY) in session.sent_messages


async def test_reports_button_then_today_callback(dp, tmp_path, monkeypatch):
    monkeypatch.setattr("handlers.report.current_day", lambda: date(2026, 10, 3))
    session = _FakeSession()
    storage = Storage(tmp_path)
    await storage.upsert_member(111, "Лід Групи", "lead", status=MEMBER_APPROVED)
    await storage.add_role(111, "group_lead")
    await storage.upsert_member(222, "Іваненко Петро", "ivan", status=MEMBER_APPROVED)
    await storage.upsert_absences_batch(222, ["2026-10-03"], "illness", None)
    bot = _make_bot(dp, storage, session)

    await dp.feed_update(bot, _message_update(1, texts.MENU_REPORTS, _user(111)))
    assert (111, texts.REPORT_PROMPT) in session.sent_messages

    await dp.feed_update(bot, _callback_update(2, "rep:today", _user(111)))
    assert any("• Іваненко Петро — 💊 хвороба" in text for _, text in session.edited_messages)


async def test_foreign_callback_reaches_stale_handler(dp, tmp_path):
    session = _FakeSession()
    storage = Storage(tmp_path)
    await storage.upsert_member(111, "Студент Тестовий", "student", status=MEMBER_APPROVED)
    bot = _make_bot(dp, storage, session)

    await dp.feed_update(bot, _callback_update(1, "unknown:data", _user(111)))

    assert (texts.STALE_CALLBACK, True) in session.answered_callbacks
