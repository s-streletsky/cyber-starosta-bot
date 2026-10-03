"""Unit tests for handlers/start.py: /start onboarding flow."""

from unittest.mock import AsyncMock

import pytest

import texts
from handlers.start import OnboardingForm, cmd_start, receive_full_name
from storage import MEMBER_APPROVED, MEMBER_PENDING, MEMBER_REMOVED, Storage
from tests.fakes import ADMIN_ID, _FakeMessage, _FakeState


# 1. Env admin without a record → approved immediately
@pytest.mark.asyncio
async def test_start_admin_gets_approved(tmp_path):
    storage = Storage(tmp_path)
    msg = _FakeMessage(from_user_id=ADMIN_ID)
    state = _FakeState()

    await cmd_start(msg, state, storage)

    assert any(texts.brand_greeting(ADMIN_ID) in t for t, _ in msg.answers)
    assert msg.answers[0][1] is not None

    member = await storage.get_member(ADMIN_ID)
    assert member is not None
    assert member["status"] == MEMBER_APPROVED


# 2. Approved member gets greeting + role menu
@pytest.mark.asyncio
async def test_start_approved_member(tmp_path):
    storage = Storage(tmp_path)
    await storage.upsert_member(111, "Студент Тестовий", "student", status=MEMBER_APPROVED)

    msg = _FakeMessage(from_user_id=111)
    state = _FakeState()
    await cmd_start(msg, state, storage)

    assert any(texts.START_IN_GROUP in t for t, _ in msg.answers)


# 3. Pending member sees the "under review" notice
@pytest.mark.asyncio
async def test_start_pending_member(tmp_path):
    storage = Storage(tmp_path)
    await storage.upsert_member(111, "Студент Тестовий", "student", status=MEMBER_PENDING)

    msg = _FakeMessage(from_user_id=111)
    state = _FakeState()
    await cmd_start(msg, state, storage)

    assert any(texts.START_PENDING in t for t, _ in msg.answers)


# 4. Removed member is invited to re-submit
@pytest.mark.asyncio
async def test_start_removed_member(tmp_path):
    storage = Storage(tmp_path)
    await storage.upsert_member(111, "Студент Тестовий", "student", status=MEMBER_REMOVED)

    msg = _FakeMessage(from_user_id=111)
    state = _FakeState()
    await cmd_start(msg, state, storage)

    assert any(texts.ONBOARDING_PROMPT in t for t, _ in msg.answers)
    assert state.set_to == OnboardingForm.full_name


# 5. Brand-new user starts onboarding
@pytest.mark.asyncio
async def test_start_new_user(tmp_path):
    storage = Storage(tmp_path)
    msg = _FakeMessage(from_user_id=111)
    state = _FakeState()

    await cmd_start(msg, state, storage)

    assert any(texts.ONBOARDING_PROMPT in t for t, _ in msg.answers)
    assert state.set_to == OnboardingForm.full_name


# 6. Valid full name → request sent, member becomes pending
@pytest.mark.asyncio
async def test_receive_full_name_valid(tmp_path, monkeypatch):
    storage = Storage(tmp_path)
    msg = _FakeMessage(from_user_id=111, text="Тестовий Студент")
    state = _FakeState()

    sentinel = AsyncMock()
    monkeypatch.setattr("handlers.start.send_request_card", sentinel)

    await receive_full_name(msg, state, storage)

    assert any(texts.START_REQUEST_SENT in t for t, _ in msg.answers)
    sentinel.assert_called_once()

    member = await storage.get_member(111)
    assert member is not None
    assert member["status"] == MEMBER_PENDING


# 7. Invalid full name → re-prompt, no state change
@pytest.mark.asyncio
async def test_receive_full_name_invalid(tmp_path):
    storage = Storage(tmp_path)
    msg = _FakeMessage(from_user_id=111, text="ОдноСлово")
    state = _FakeState()

    await receive_full_name(msg, state, storage)

    assert any(texts.ONBOARDING_PROMPT in t for t, _ in msg.answers)

