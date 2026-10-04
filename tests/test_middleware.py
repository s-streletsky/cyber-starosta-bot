"""M14: the onboarding bypass predicate matches exactly one state."""

from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

import texts
from handlers.middleware import AccessControlMiddleware, is_onboarding_state, is_open_command
from handlers.start import OnboardingForm
from services.help import AUDIENCE_ALL, HELP_COMMANDS, OPEN_COMMANDS
from storage import MEMBER_APPROVED, MEMBER_PENDING, MEMBER_REMOVED, Storage
from tests.fakes import ADMIN_ID, _FakeCallback, _FakeMessage


def test_exact_onboarding_state_matches():
    assert is_onboarding_state(OnboardingForm.full_name) is True
    assert is_onboarding_state(OnboardingForm.full_name.state) is True


def test_similar_states_do_not_match():
    assert is_onboarding_state(None) is False
    assert is_onboarding_state("") is False
    assert is_onboarding_state("OnboardingForm:full_name:extra") is False
    assert is_onboarding_state("AbsenceForm:day") is False


def test_open_commands_policy_is_exactly_start_and_help():
    assert OPEN_COMMANDS == {"start", "help"}


def test_open_commands_derived_from_catalog_audience_all():
    assert OPEN_COMMANDS == {
        entry.command for entry in HELP_COMMANDS if entry.audience == AUDIENCE_ALL
    }


@pytest.mark.parametrize(
    "text",
    ["/start", "/start@my_bot", "/help", "/help@my_bot", "  /help  ", "/start extra", "/help x"],
)
def test_is_open_command_true(text):
    assert is_open_command(text) is True


@pytest.mark.parametrize(
    "text",
    [
        "start",
        "help",
        "//start",
        "///help",
        "/helpx",
        "/pending",
        "/promote",
        None,
        "",
        "   ",
        "\t",
        "\n",
        "\xa0",
        "/HELP",
    ],
)
def test_is_open_command_false(text):
    assert is_open_command(text) is False


# --- AccessControlMiddleware.__call__ ---


async def _run_middleware(storage, event, raw_state=None):
    handler = AsyncMock(return_value="handled")
    bot = AsyncMock()
    bot.get_chat = AsyncMock(return_value=SimpleNamespace(username=None))
    data = {"storage": storage, "bot": bot, "raw_state": raw_state}
    result = await AccessControlMiddleware()(handler, event, data)
    return handler, result


@pytest.mark.asyncio
async def test_admin_bypasses_acl(tmp_path):
    event = SimpleNamespace(message=_FakeMessage(ADMIN_ID, text="hello"), callback_query=None)
    handler, _ = await _run_middleware(Storage(tmp_path), event)

    handler.assert_called_once()


@pytest.mark.asyncio
async def test_start_open_for_unknown(tmp_path):
    event = SimpleNamespace(message=_FakeMessage(111, text="/start"), callback_query=None)
    handler, _ = await _run_middleware(Storage(tmp_path), event)

    handler.assert_called_once()


@pytest.mark.asyncio
async def test_start_at_bot_suffix_open(tmp_path):
    event = SimpleNamespace(message=_FakeMessage(111, text="/start@my_bot"), callback_query=None)
    handler, _ = await _run_middleware(Storage(tmp_path), event)

    handler.assert_called_once()


@pytest.mark.asyncio
async def test_help_open_for_unknown(tmp_path):
    event = SimpleNamespace(message=_FakeMessage(111, text="/help"), callback_query=None)
    handler, _ = await _run_middleware(Storage(tmp_path), event)

    handler.assert_called_once()


@pytest.mark.asyncio
async def test_help_at_bot_suffix_open(tmp_path):
    event = SimpleNamespace(message=_FakeMessage(111, text="/help@my_bot"), callback_query=None)
    handler, _ = await _run_middleware(Storage(tmp_path), event)

    handler.assert_called_once()


@pytest.mark.asyncio
async def test_pending_denied_for_pending_member(tmp_path):
    storage = Storage(tmp_path)
    await storage.upsert_member(111, "Студент Тестовий", "student", status=MEMBER_PENDING)
    message = _FakeMessage(111, text="/pending")
    event = SimpleNamespace(message=message, callback_query=None)
    handler, _ = await _run_middleware(storage, event)

    handler.assert_not_called()
    assert any(texts.ACCESS_DENIED == text for text, _ in message.answers)


@pytest.mark.asyncio
async def test_onboarding_state_bypass(tmp_path):
    event = SimpleNamespace(message=_FakeMessage(111, text="Петренко Іван"), callback_query=None)
    handler, _ = await _run_middleware(
        Storage(tmp_path), event, raw_state=OnboardingForm.full_name.state
    )

    handler.assert_called_once()


@pytest.mark.asyncio
async def test_approved_member_allowed(tmp_path):
    storage = Storage(tmp_path)
    await storage.upsert_member(111, "Студент Тестовий", "student", status=MEMBER_APPROVED)
    event = SimpleNamespace(message=_FakeMessage(111, text="привет"), callback_query=None)
    handler, _ = await _run_middleware(storage, event)

    handler.assert_called_once()


@pytest.mark.asyncio
async def test_pending_member_message_denied(tmp_path):
    storage = Storage(tmp_path)
    await storage.upsert_member(111, "Студент Тестовий", "student", status=MEMBER_PENDING)
    message = _FakeMessage(111, text="привет")
    event = SimpleNamespace(message=message, callback_query=None)
    handler, _ = await _run_middleware(storage, event)

    handler.assert_not_called()
    assert any(texts.ACCESS_DENIED == text for text, _ in message.answers)


@pytest.mark.asyncio
async def test_removed_member_callback_denied(tmp_path):
    storage = Storage(tmp_path)
    await storage.upsert_member(111, "Студент Тестовий", "student", status=MEMBER_REMOVED)
    callback = _FakeCallback(111)
    event = SimpleNamespace(message=None, callback_query=callback)
    handler, _ = await _run_middleware(storage, event)

    handler.assert_not_called()
    assert any(
        args and args[0] == texts.ACCESS_DENIED and kwargs.get("show_alert") is True
        for args, kwargs in callback.answers
    )


@pytest.mark.asyncio
async def test_approved_callback_allowed(tmp_path):
    storage = Storage(tmp_path)
    await storage.upsert_member(111, "Студент Тестовий", "student", status=MEMBER_APPROVED)
    callback = _FakeCallback(111)
    event = SimpleNamespace(message=None, callback_query=callback)
    handler, _ = await _run_middleware(storage, event)

    handler.assert_called_once()


@pytest.mark.asyncio
async def test_no_from_user_passthrough(tmp_path):
    message = _FakeMessage(111, text="привет")
    message.from_user = None
    event = SimpleNamespace(message=message, callback_query=None)
    handler, _ = await _run_middleware(Storage(tmp_path), event)

    handler.assert_called_once()


@pytest.mark.asyncio
async def test_storage_none_denies_non_admin(tmp_path):
    message = _FakeMessage(111, text="привет")
    event = SimpleNamespace(message=message, callback_query=None)
    handler, _ = await _run_middleware(None, event)

    handler.assert_not_called()
    assert any(texts.ACCESS_DENIED == text for text, _ in message.answers)

