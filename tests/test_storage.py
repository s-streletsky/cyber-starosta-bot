"""Tests for Storage: JSONL absence storage and roster upsert."""

import json

from storage import Storage


def _line(record: dict) -> str:
    return json.dumps(record, ensure_ascii=False)


async def test_upsert_absence_created_replaced_identical(tmp_path):
    storage = Storage(tmp_path)

    assert (await storage.upsert_absences_batch(1, ["2026-09-29"], "illness", None)) == ["created"]
    assert (await storage.upsert_absences_batch(1, ["2026-09-29"], "family", None)) == ["replaced"]
    assert (await storage.upsert_absences_batch(1, ["2026-09-29"], "family", None)) == ["identical"]
    assert (
        await storage.upsert_absences_batch(1, ["2026-09-29"], "other", "пробки")
    ) == ["replaced"]
    assert (
        await storage.upsert_absences_batch(1, ["2026-09-29"], "other", "пробки")
    ) == ["identical"]
    assert (await storage.upsert_absences_batch(2, ["2026-09-29"], "illness", None)) == ["created"]


async def test_identical_record_is_not_appended(tmp_path):
    storage = Storage(tmp_path)

    await storage.upsert_absences_batch(1, ["2026-09-29"], "illness", None)
    await storage.upsert_absences_batch(1, ["2026-09-29"], "illness", None)

    raw = (tmp_path / "absences.jsonl").read_text(encoding="utf-8")
    assert len(raw.splitlines()) == 1


async def test_index_prefers_last_line(tmp_path):
    records = [
        {
            "user_id": 1,
            "date": "2026-09-29",
            "reason": "illness",
            "reason_text": None,
            "created_at": "2026-09-28T10:00:00Z",
        },
        {
            "user_id": 1,
            "date": "2026-09-29",
            "reason": "family",
            "reason_text": None,
            "created_at": "2026-09-28T11:00:00Z",
        },
    ]
    (tmp_path / "absences.jsonl").write_text(
        "\n".join(_line(record) for record in records) + "\n", encoding="utf-8"
    )

    storage = Storage(tmp_path)

    record = await storage.get_record(1, "2026-09-29")
    assert record is not None
    assert record["reason"] == "family"


async def test_broken_lines_are_skipped(tmp_path):
    good = {
        "user_id": 7,
        "date": "2026-10-01",
        "reason": "event",
        "reason_text": None,
        "created_at": "2026-09-28T10:00:00Z",
    }
    content = "\n".join(["не json", _line(good), '{"user_id": "сміття"}', ""]) + "\n"
    (tmp_path / "absences.jsonl").write_text(content, encoding="utf-8")

    storage = Storage(tmp_path)

    assert await storage.get_record(7, "2026-10-01") is not None
    assert await storage.get_record(1, "2026-09-29") is None


async def test_append_is_real_and_uses_lf_utf8(tmp_path):
    storage = Storage(tmp_path)

    for offset in range(3):
        date_iso = f"2026-10-0{offset + 1}"
        assert (await storage.upsert_absences_batch(1, [date_iso], "illness", None)) == ["created"]

    raw = (tmp_path / "absences.jsonl").read_bytes()
    text = raw.decode("utf-8")

    assert b"\r" not in raw
    lines = text.splitlines()
    assert len(lines) == 3
    for line in lines:
        json.loads(line)
    assert text.endswith("\n")


async def test_get_record_returns_none_for_missing_key(tmp_path):
    storage = Storage(tmp_path)

    assert await storage.get_record(42, "2026-09-29") is None


async def test_upsert_absences_batch_statuses_and_append_count(tmp_path):
    storage = Storage(tmp_path)

    assert await storage.upsert_absences_batch(
        1, ["2026-09-29", "2026-09-30"], "illness", None
    ) == ["created", "created"]
    assert await storage.upsert_absences_batch(
        1, ["2026-09-29", "2026-10-01"], "family", None
    ) == ["replaced", "created"]
    assert await storage.upsert_absences_batch(1, ["2026-09-29"], "family", None) == ["identical"]

    raw = (tmp_path / "absences.jsonl").read_text(encoding="utf-8")
    assert len(raw.splitlines()) == 4   # identical record is not appended


async def test_member_created_then_username_updates_only(tmp_path):
    storage = Storage(tmp_path)

    assert await storage.upsert_member(1, "Іван Іванів", "ivan") == "created"
    assert await storage.upsert_member(1, "Інше Ім'я", "new_name") == "updated"

    member = await storage.get_member(1)
    assert member["display_name"] == "Іван Іванів"
    assert member["username"] == "new_name"


async def test_member_upsert_reads_file_from_disk(tmp_path):
    storage = Storage(tmp_path)
    await storage.upsert_member(1, "Іван Іванів", "ivan")

    # The roster was edited outside the bot — the upsert must see it.
    external = {"1": {"display_name": "Виправлено старостою", "username": "ivan"}}
    (tmp_path / "members.json").write_text(
        json.dumps(external, ensure_ascii=False), encoding="utf-8"
    )

    await storage.upsert_member(1, "Іван Іванів", "ivan_updated")

    member = await storage.get_member(1)
    assert member["display_name"] == "Виправлено старостою"
    assert member["username"] == "ivan_updated"


async def test_member_missing_file_returns_none(tmp_path):
    storage = Storage(tmp_path)

    assert await storage.get_member(1) is None


async def test_list_absences_for_date_filters_excludes_and_copies(tmp_path):
    storage = Storage(tmp_path)
    await storage.upsert_absences_batch(1, ["2026-10-03"], "illness", None)
    await storage.upsert_absences_batch(2, ["2026-10-03"], "event", None)
    await storage.upsert_absences_batch(3, ["2026-10-04"], "family", None)

    records = await storage.list_absences_for_date("2026-10-03")
    by_user = {user_id: record for user_id, record in records}

    assert set(by_user) == {1, 2}
    assert by_user[1]["reason"] == "illness"
    assert by_user[2]["reason"] == "event"

    # Mutating a returned record must not affect a later read.
    by_user[1]["reason"] = "tampered"
    reread = await storage.list_absences_for_date("2026-10-03")
    again = {user_id: record for user_id, record in reread}
    assert again[1]["reason"] == "illness"


async def test_list_absences_for_date_empty(tmp_path):
    storage = Storage(tmp_path)

    assert await storage.list_absences_for_date("2026-10-03") == []
