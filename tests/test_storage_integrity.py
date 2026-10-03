"""K1: members.json read states (missing/ok/corrupt) and PII in logs."""

import json
import logging

import pytest

from storage import Storage, StorageCorruptError


def _corrupt(path) -> None:
    path.write_text("{not valid json", encoding="utf-8")


async def test_missing_files_are_read_as_empty(tmp_path):
    storage = Storage(tmp_path)

    assert await storage.get_member(1) is None
    assert await storage.list_members() == []
    assert await storage.get_head_lead() is None


async def test_corrupt_members_is_read_as_empty_without_raising(tmp_path, caplog):
    _corrupt(tmp_path / "members.json")
    storage = Storage(tmp_path)

    with caplog.at_level(logging.ERROR):
        assert await storage.get_member(1) is None
        assert await storage.list_members() == []

    assert "members.json" in caplog.text


async def test_corrupt_members_write_raises_and_snapshots_once(tmp_path):
    _corrupt(tmp_path / "members.json")
    storage = Storage(tmp_path)

    with pytest.raises(StorageCorruptError):
        await storage.upsert_member(1, "Петренко Іван", "ivan")
    with pytest.raises(StorageCorruptError):
        await storage.upsert_member(2, "Сидоренко Оля", "olya")

    snapshots = list(tmp_path.glob("members.corrupt-*.json"))
    assert len(snapshots) == 1
    assert snapshots[0].read_text(encoding="utf-8") == "{not valid json"


async def test_valid_members_file_still_works(tmp_path):
    members = {"1": {"display_name": "Іван", "username": "ivan", "status": "approved", "roles": []}}
    (tmp_path / "members.json").write_text(json.dumps(members), encoding="utf-8")

    storage = Storage(tmp_path)

    assert await storage.get_member(1) is not None


async def test_broken_absence_line_does_not_leak_content_to_logs(tmp_path, caplog):
    secret = "SECRET-PII-1234567890-DO-NOT-LOG"
    (tmp_path / "absences.jsonl").write_text(secret + "\n", encoding="utf-8")

    with caplog.at_level(logging.WARNING):
        Storage(tmp_path)

    assert secret not in caplog.text
    assert "absences" in caplog.text
