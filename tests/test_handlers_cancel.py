"""Unit tests for handlers/cancel.py: the global /cancel command."""

import pytest

import texts
from handlers.absence import AbsenceForm
from handlers.cancel import cancel_any
from handlers.start import OnboardingForm
from storage import Storage
from tests.fakes import _FakeMessage, _FakeState


@pytest.mark.asyncio
async def test_cancel_absence_state_clears_and_replies(tmp_path):
    storage = Storage(tmp_path)
    msg = _FakeMessage(from_user_id=111)
    state = _FakeState()
    await state.set_state(AbsenceForm.day)

    await cancel_any(msg, state, storage)

    assert state.cleared
    assert msg.answers[0][0] == texts.CANCELLED
    assert msg.answers[0][1] is not None


@pytest.mark.asyncio
async def test_cancel_onboarding_state_clears_and_replies(tmp_path):
    storage = Storage(tmp_path)
    msg = _FakeMessage(from_user_id=111)
    state = _FakeState()
    await state.set_state(OnboardingForm.full_name)

    await cancel_any(msg, state, storage)

    assert state.cleared
    assert msg.answers[0][0] == texts.CANCELLED


@pytest.mark.asyncio
async def test_cancel_without_active_state_reports_nothing_to_cancel(tmp_path):
    storage = Storage(tmp_path)
    msg = _FakeMessage(from_user_id=111)
    state = _FakeState()

    await cancel_any(msg, state, storage)

    assert state.cleared
    assert msg.answers[0][0] == texts.NOTHING_TO_CANCEL
    assert msg.answers[0][1] is not None
