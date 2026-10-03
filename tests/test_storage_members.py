"""Tests for roles/statuses: onboarding requests, approve/reject/remove, roles, head lead.

Old members.json files without status/roles fields are read with defaults
(status=approved, roles=[]), no on-disk migration needed. The head lead is the
optional boolean `is_head_lead` on a roster entry.
"""

import json

from storage import MEMBER_APPROVED, MEMBER_PENDING, MEMBER_REMOVED, Storage


def _write_members(tmp_path, members: dict) -> None:
    (tmp_path / "members.json").write_text(
        json.dumps(members, ensure_ascii=False), encoding="utf-8"
    )


def _read_members(tmp_path) -> dict:
    return json.loads((tmp_path / "members.json").read_text(encoding="utf-8"))


async def test_new_member_defaults_to_pending(tmp_path):
    storage = Storage(tmp_path)

    await storage.upsert_member(1, "Петренко Іван", "ivan")

    member = await storage.get_member(1)
    assert member["status"] == MEMBER_PENDING
    assert member["roles"] == []


async def test_upsert_member_keeps_status_and_roles(tmp_path):
    storage = Storage(tmp_path)
    await storage.upsert_member(1, "Петренко Іван", "ivan")
    await storage.approve_pending(1)
    await storage.add_role(1, "group_lead")

    await storage.upsert_member(1, "Інше Ім'я", "ivan_new")

    member = await storage.get_member(1)
    assert member["display_name"] == "Петренко Іван"
    assert member["username"] == "ivan_new"
    assert member["status"] == MEMBER_APPROVED
    assert member["roles"] == ["group_lead"]


async def test_legacy_member_file_defaults_approved(tmp_path):
    _write_members(tmp_path, {"1": {"display_name": "Старий запис", "username": "old"}})

    storage = Storage(tmp_path)

    member = await storage.get_member(1)
    assert member["status"] == MEMBER_APPROVED
    assert member["roles"] == []


async def test_removed_member_keeps_record_and_history_possible(tmp_path):
    storage = Storage(tmp_path)
    await storage.upsert_member(1, "Петренко Іван", "ivan")
    await storage.approve_pending(1)

    assert await storage.remove_member(1) is True

    member = await storage.get_member(1)
    assert member["status"] == MEMBER_REMOVED
    assert member["display_name"] == "Петренко Іван"


async def test_resubmit_member_reapplies_with_new_name(tmp_path):
    storage = Storage(tmp_path)
    await storage.upsert_member(1, "Петренко Іван", "ivan")
    await storage.approve_pending(1)
    await storage.remove_member(1)

    await storage.resubmit_member(1, "Нове Ім'я", "ivan2")

    member = await storage.get_member(1)
    assert member["status"] == MEMBER_PENDING
    assert member["display_name"] == "Нове Ім'я"
    assert member["username"] == "ivan2"


async def test_resubmit_member_creates_if_missing(tmp_path):
    storage = Storage(tmp_path)

    await storage.resubmit_member(1, "Нове Ім'я", None)

    member = await storage.get_member(1)
    assert member["status"] == MEMBER_PENDING
    assert member["roles"] == []


async def test_resubmit_member_drops_head_lead_flag(tmp_path):
    storage = Storage(tmp_path)
    await storage.upsert_member(7, "Петренко Іван", "ivan")
    await storage.approve_pending(7)
    await storage.set_head_lead(7)

    await storage.resubmit_member(7, "Петренко Іван", "ivan")

    assert "is_head_lead" not in _read_members(tmp_path)["7"]
    assert await storage.get_head_lead() is None


async def test_add_and_remove_role(tmp_path):
    storage = Storage(tmp_path)
    await storage.upsert_member(1, "Петренко Іван", "ivan")

    roles = await storage.add_role(1, "group_lead")
    assert roles == ["group_lead"]
    assert await storage.add_role(1, "group_lead") == ["group_lead"]

    assert await storage.add_role(1, "supervisor") == ["group_lead", "supervisor"]
    assert await storage.remove_role(1, "group_lead") == ["supervisor"]
    assert await storage.remove_role(1, "group_lead") == ["supervisor"]

    await storage.remove_role(1, "supervisor")
    assert (await storage.get_member(1))["roles"] == []


async def test_roles_require_member(tmp_path):
    storage = Storage(tmp_path)

    assert await storage.add_role(42, "group_lead") is None
    assert await storage.remove_role(42, "group_lead") is None


async def test_list_members_filters(tmp_path):
    storage = Storage(tmp_path)
    await storage.upsert_member(1, "А", "a")
    await storage.upsert_member(2, "Б", "b")
    await storage.approve_pending(2)
    await storage.upsert_member(3, "В", "c")
    await storage.approve_pending(3)
    await storage.add_role(3, "group_lead")
    await storage.remove_member(3)

    pending = await storage.list_members(status="pending")
    approved = await storage.list_members(status=MEMBER_APPROVED)
    leads = await storage.list_members(status=MEMBER_APPROVED, role="group_lead")

    assert [user_id for user_id, _ in pending] == [1]
    assert [user_id for user_id, _ in approved] == [2]
    assert leads == []


async def test_list_members_skips_bad_keys(tmp_path):
    _write_members(tmp_path, {"not-an-id": {"display_name": "Сміття", "status": MEMBER_APPROVED}})

    storage = Storage(tmp_path)

    assert await storage.list_members() == []


async def test_head_lead_roundtrip_marks_member_record(tmp_path):
    storage = Storage(tmp_path)
    await storage.upsert_member(7, "Петренко Іван", "ivan")

    assert await storage.get_head_lead() is None

    assert await storage.set_head_lead(7) == 7
    assert await storage.get_head_lead() == 7
    assert _read_members(tmp_path)["7"]["is_head_lead"] is True

    assert await storage.set_head_lead(None) is None
    assert await storage.get_head_lead() is None
    assert "is_head_lead" not in _read_members(tmp_path)["7"]


async def test_set_head_lead_needs_an_existing_member(tmp_path):
    storage = Storage(tmp_path)

    assert await storage.set_head_lead(7) is None
    assert await storage.get_head_lead() is None


async def test_set_head_lead_switches_flag_to_the_new_member(tmp_path):
    storage = Storage(tmp_path)
    await storage.upsert_member(1, "Петренко Іван", "ivan")
    await storage.upsert_member(2, "Сидоренко Оля", "olya")

    await storage.set_head_lead(1)
    await storage.set_head_lead(2)

    members = _read_members(tmp_path)
    assert await storage.get_head_lead() == 2
    assert members["1"].get("is_head_lead") is not True
    assert members["2"]["is_head_lead"] is True
    assert sum(1 for m in members.values() if m.get("is_head_lead") is True) == 1


async def test_head_lead_survives_storage_restart(tmp_path):
    storage = Storage(tmp_path)
    await storage.upsert_member(7, "Петренко Іван", "ivan")
    await storage.set_head_lead(7)

    fresh = Storage(tmp_path)

    assert await fresh.get_head_lead() == 7


async def test_head_lead_reads_external_edits(tmp_path):
    storage = Storage(tmp_path)
    await storage.upsert_member(7, "Петренко Іван", "ivan")
    _write_members(
        tmp_path,
        {"7": {"display_name": "Петренко Іван", "username": "ivan", "is_head_lead": True}},
    )

    assert await storage.get_head_lead() == 7


async def test_get_head_lead_warns_and_keeps_first_of_duplicate_flags(tmp_path, caplog):
    _write_members(
        tmp_path,
        {
            "1": {"display_name": "Перший", "status": MEMBER_APPROVED, "is_head_lead": True},
            "2": {"display_name": "Другий", "status": MEMBER_APPROVED, "is_head_lead": True},
        },
    )
    storage = Storage(tmp_path)

    with caplog.at_level("WARNING"):
        assert await storage.get_head_lead() == 1

    assert "Multiple is_head_lead flags" in caplog.text


async def test_upsert_member_can_create_approved(tmp_path):
    storage = Storage(tmp_path)

    await storage.upsert_member(1, "Адмін Адмін", "admin", status=MEMBER_APPROVED)

    member = await storage.get_member(1)
    assert member["status"] == MEMBER_APPROVED
    assert member["roles"] == []


async def test_remove_member_clears_roles_and_head_lead(tmp_path):
    storage = Storage(tmp_path)
    await storage.upsert_member(1, "Петренко Іван", "ivan")
    await storage.approve_pending(1)
    await storage.add_role(1, "group_lead")
    await storage.set_head_lead(1)

    assert await storage.remove_member(1) is True

    member = await storage.get_member(1)
    assert member["status"] == MEMBER_REMOVED
    assert member["roles"] == []
    assert await storage.get_head_lead() is None


async def test_approve_pending_result_codes(tmp_path):
    storage = Storage(tmp_path)
    await storage.upsert_member(1, "Петренко Іван", "ivan")

    assert await storage.approve_pending(1) == "approved"
    assert await storage.approve_pending(1) == "not_pending"
    assert await storage.approve_pending(42) == "missing"


async def test_reject_pending_result_codes(tmp_path):
    storage = Storage(tmp_path)
    await storage.upsert_member(1, "Петренко Іван", "ivan")

    assert await storage.reject_pending(1) == "rejected"
    assert await storage.reject_pending(1) == "missing"
