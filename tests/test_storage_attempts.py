"""Tests for the per-date lifetime mutation attempt limit in the absences journal."""

import asyncio
import json

from storage import (
    ABSENCE_ATTEMPT_LIMIT,
    ABSENCE_DELETED,
    ABSENCE_IDENTICAL,
    ABSENCE_LIMIT,
    Storage,
)


def _lines(tmp_path) -> list[str]:
    path = tmp_path / "absences.jsonl"
    if not path.exists():
        return []
    return path.read_text(encoding="utf-8").splitlines()


async def test_mutations_consume_and_count_reflects_it(tmp_path):
    storage = Storage(tmp_path)

    await storage.upsert_absences_batch(1, ["2026-10-03"], "illness", None)
    assert await storage.count_day_attempts(1, "2026-10-03") == 1

    await storage.upsert_absences_batch(1, ["2026-10-03"], "family", None)
    assert await storage.count_day_attempts(1, "2026-10-03") == 2

    await storage.delete_absences_batch(1, ["2026-10-03"])
    assert await storage.count_day_attempts(1, "2026-10-03") == 3
    assert len(_lines(tmp_path)) == 3


async def test_identical_consumes_nothing_and_appends_nothing(tmp_path):
    storage = Storage(tmp_path)
    await storage.upsert_absences_batch(1, ["2026-10-03"], "illness", None)

    assert await storage.upsert_absences_batch(1, ["2026-10-03"], "illness", None) == [
        ABSENCE_IDENTICAL
    ]

    assert await storage.count_day_attempts(1, "2026-10-03") == 1
    assert len(_lines(tmp_path)) == 1


async def test_eleventh_mutation_is_limited_and_appends_nothing(tmp_path):
    storage = Storage(tmp_path)
    for index in range(ABSENCE_ATTEMPT_LIMIT):
        result = await storage.upsert_absences_batch(1, ["2026-10-03"], "illness", f"text-{index}")
        assert result == ["created" if index == 0 else "replaced"]
    lines_before = len(_lines(tmp_path))

    assert await storage.upsert_absences_batch(1, ["2026-10-03"], "family", None) == [ABSENCE_LIMIT]

    assert len(_lines(tmp_path)) == lines_before
    assert await storage.count_day_attempts(1, "2026-10-03") == ABSENCE_ATTEMPT_LIMIT


async def test_counter_rebuilt_from_journal_on_reload(tmp_path):
    storage = Storage(tmp_path)
    for index in range(3):
        await storage.upsert_absences_batch(1, ["2026-10-03"], "illness", f"text-{index}")

    reloaded = Storage(tmp_path)

    assert await reloaded.count_day_attempts(1, "2026-10-03") == 3


async def test_batch_with_one_limited_and_one_free_date(tmp_path):
    storage = Storage(tmp_path)
    for index in range(ABSENCE_ATTEMPT_LIMIT):
        await storage.upsert_absences_batch(1, ["2026-10-03"], "illness", f"text-{index}")
    lines_before = len(_lines(tmp_path))

    results = await storage.upsert_absences_batch(1, ["2026-10-03", "2026-10-04"], "family", None)

    assert results == [ABSENCE_LIMIT, "created"]
    assert len(_lines(tmp_path)) == lines_before + 1


async def test_delete_at_limit_is_blocked_and_keeps_record(tmp_path):
    storage = Storage(tmp_path)
    for index in range(ABSENCE_ATTEMPT_LIMIT):
        await storage.upsert_absences_batch(1, ["2026-10-03"], "illness", f"text-{index}")
    lines_before = len(_lines(tmp_path))

    assert await storage.delete_absences_batch(1, ["2026-10-03"]) == [ABSENCE_LIMIT]

    assert len(_lines(tmp_path)) == lines_before
    assert await storage.get_record(1, "2026-10-03") is not None


async def test_delete_then_remark_consumes_two(tmp_path):
    storage = Storage(tmp_path)
    await storage.upsert_absences_batch(1, ["2026-10-03"], "illness", None)
    assert await storage.count_day_attempts(1, "2026-10-03") == 1

    await storage.delete_absences_batch(1, ["2026-10-03"])
    assert await storage.count_day_attempts(1, "2026-10-03") == 2

    await storage.upsert_absences_batch(1, ["2026-10-03"], "family", None)
    assert await storage.count_day_attempts(1, "2026-10-03") == 3


async def test_preseeded_journal_at_limit_behaves_as_limited(tmp_path):
    path = tmp_path / "absences.jsonl"
    record = {"user_id": 1, "date": "2026-10-03", "reason": "illness", "reason_text": None}
    path.write_text("\n".join(json.dumps(record) for _ in range(10)) + "\n", encoding="utf-8")

    storage = Storage(tmp_path)

    assert await storage.count_day_attempts(1, "2026-10-03") == 10
    assert await storage.upsert_absences_batch(1, ["2026-10-03"], "family", None) == [ABSENCE_LIMIT]
    assert len(_lines(tmp_path)) == 10


async def test_broken_lines_are_skipped_and_not_counted(tmp_path):
    path = tmp_path / "absences.jsonl"
    valid = json.dumps(
        {"user_id": 1, "date": "2026-10-03", "reason": "illness", "reason_text": None}
    )
    path.write_text(
        "not json\n" + valid + "\n" + json.dumps({"user_id": 1}) + "\n",
        encoding="utf-8",
    )

    storage = Storage(tmp_path)

    assert await storage.count_day_attempts(1, "2026-10-03") == 1


async def test_enforce_limit_false_bypasses_cap(tmp_path):
    storage = Storage(tmp_path)
    for index in range(ABSENCE_ATTEMPT_LIMIT):
        await storage.upsert_absences_batch(1, ["2026-10-03"], "illness", f"text-{index}")
    lines_before = len(_lines(tmp_path))

    result = await storage.upsert_absences_batch(
        1, ["2026-10-03"], "family", None, enforce_limit=False
    )

    assert result == ["replaced"]
    assert len(_lines(tmp_path)) == lines_before + 1
    assert await storage.delete_absences_batch(1, ["2026-10-03"], enforce_limit=False) == [
        ABSENCE_DELETED
    ]


async def test_concurrent_boundary_never_exceeds_limit(tmp_path):
    storage = Storage(tmp_path)

    results = await asyncio.gather(
        *(
            storage.upsert_absences_batch(1, ["2026-10-03"], "illness", f"text-{index}")
            for index in range(ABSENCE_ATTEMPT_LIMIT + 2)
        )
    )

    flat = [result for batch in results for result in batch]
    assert len(_lines(tmp_path)) == ABSENCE_ATTEMPT_LIMIT
    assert ABSENCE_LIMIT in flat
