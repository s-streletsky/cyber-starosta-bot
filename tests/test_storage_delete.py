"""Tests for logical deletion (tombstones) in the absences journal."""

import asyncio
import json

from storage import ABSENCE_DELETED, ABSENCE_IDENTICAL, Storage, is_deleted


def _lines(tmp_path) -> list[str]:
    path = tmp_path / "absences.jsonl"
    if not path.exists():
        return []
    return path.read_text(encoding="utf-8").splitlines()


async def test_delete_existing_appends_tombstone_and_reads_as_absent(tmp_path):
    storage = Storage(tmp_path)
    await storage.upsert_absences_batch(1, ["2026-10-03"], "illness", None)

    assert await storage.delete_absences_batch(1, ["2026-10-03"]) == [ABSENCE_DELETED]

    assert await storage.get_record(1, "2026-10-03") is None
    assert await storage.list_absences_for_date("2026-10-03") == []
    assert len(_lines(tmp_path)) == 2


async def test_delete_missing_is_identical_and_appends_nothing(tmp_path):
    storage = Storage(tmp_path)

    assert await storage.delete_absences_batch(1, ["2026-10-03"]) == [ABSENCE_IDENTICAL]

    assert _lines(tmp_path) == []


async def test_delete_twice_appends_only_once(tmp_path):
    storage = Storage(tmp_path)
    await storage.upsert_absences_batch(1, ["2026-10-03"], "illness", None)

    assert await storage.delete_absences_batch(1, ["2026-10-03"]) == [ABSENCE_DELETED]
    assert await storage.delete_absences_batch(1, ["2026-10-03"]) == [ABSENCE_IDENTICAL]

    assert len(_lines(tmp_path)) == 2


async def test_reupsert_after_delete_creates_and_reappears(tmp_path):
    storage = Storage(tmp_path)
    await storage.upsert_absences_batch(1, ["2026-10-03"], "illness", None)
    await storage.delete_absences_batch(1, ["2026-10-03"])

    assert await storage.upsert_absences_batch(1, ["2026-10-03"], "family", None) == ["created"]

    record = await storage.get_record(1, "2026-10-03")
    assert record is not None
    assert record["reason"] == "family"
    assert not is_deleted(record)


async def test_reload_from_disk_preserves_tombstone(tmp_path):
    storage = Storage(tmp_path)
    await storage.upsert_absences_batch(1, ["2026-10-03"], "illness", None)
    await storage.delete_absences_batch(1, ["2026-10-03"])

    reloaded = Storage(tmp_path)

    assert await reloaded.get_record(1, "2026-10-03") is None
    assert await reloaded.list_absences_for_date("2026-10-03") == []


async def test_concurrent_delete_and_upsert_leave_consistent_last_winner(tmp_path):
    storage = Storage(tmp_path)
    await storage.upsert_absences_batch(1, ["2026-10-03"], "illness", None)

    await asyncio.gather(
        storage.delete_absences_batch(1, ["2026-10-03"]),
        storage.upsert_absences_batch(1, ["2026-10-03"], "family", None),
    )

    lines = _lines(tmp_path)
    assert len(lines) == 3  # initial + delete tombstone + upsert record (order may vary)
    last = json.loads(lines[-1])
    record = await storage.get_record(1, "2026-10-03")
    if is_deleted(last):
        assert record is None
    else:
        assert record is not None and record["reason"] == "family"


async def test_delete_tombstone_is_lf_utf8_and_append_only(tmp_path):
    storage = Storage(tmp_path)
    await storage.upsert_absences_batch(1, ["2026-10-03"], "illness", None)
    await storage.delete_absences_batch(1, ["2026-10-03"])

    raw = (tmp_path / "absences.jsonl").read_bytes()
    assert b"\r" not in raw
    text = raw.decode("utf-8")
    assert text.endswith("\n")
    assert json.loads(text.splitlines()[-1])["deleted"] is True
