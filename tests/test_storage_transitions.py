"""S3: idempotent, atomic approve/reject of pending requests."""

import asyncio

from storage import (
    MEMBER_APPROVED,
    MEMBER_REMOVED,
    RESULT_APPROVED,
    RESULT_MISSING,
    RESULT_NOT_PENDING,
    RESULT_REJECTED,
    Storage,
)


async def _pending(tmp_path, user_id: int = 1) -> Storage:
    storage = Storage(tmp_path)
    await storage.upsert_member(user_id, "Петренко Іван", "ivan")
    return storage


async def test_approve_pending_transitions_only_from_pending(tmp_path):
    storage = await _pending(tmp_path)

    assert await storage.approve_pending(1) == RESULT_APPROVED
    assert (await storage.get_member(1))["status"] == MEMBER_APPROVED
    assert await storage.approve_pending(1) == RESULT_NOT_PENDING
    assert await storage.approve_pending(42) == RESULT_MISSING


async def test_approve_pending_does_not_touch_removed(tmp_path):
    storage = await _pending(tmp_path)
    await storage.approve_pending(1)
    await storage.remove_member(1)

    assert await storage.approve_pending(1) == RESULT_NOT_PENDING
    assert (await storage.get_member(1))["status"] == MEMBER_REMOVED


async def test_concurrent_approve_pending_has_exactly_one_winner(tmp_path):
    storage = await _pending(tmp_path)

    results = await asyncio.gather(storage.approve_pending(1), storage.approve_pending(1))

    assert results.count(RESULT_APPROVED) == 1
    assert RESULT_NOT_PENDING in results


async def test_reject_pending_deletes_only_pending(tmp_path):
    storage = await _pending(tmp_path)

    assert await storage.reject_pending(1) == RESULT_REJECTED
    assert await storage.get_member(1) is None
    assert await storage.reject_pending(1) == RESULT_MISSING


async def test_reject_pending_keeps_non_pending(tmp_path):
    storage = await _pending(tmp_path)
    await storage.approve_pending(1)

    assert await storage.reject_pending(1) == RESULT_NOT_PENDING
    assert (await storage.get_member(1))["status"] == MEMBER_APPROVED


async def test_accept_and_reject_race_leaves_consistent_state(tmp_path):
    storage = await _pending(tmp_path)

    results = await asyncio.gather(storage.approve_pending(1), storage.reject_pending(1))

    member = await storage.get_member(1)
    if RESULT_APPROVED in results:
        assert sorted(results) == sorted([RESULT_APPROVED, RESULT_NOT_PENDING])
        assert member is not None and member["status"] == MEMBER_APPROVED
    else:
        assert sorted(results) == sorted([RESULT_NOT_PENDING, RESULT_REJECTED])
        assert member is None
