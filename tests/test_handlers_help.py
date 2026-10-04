"""Unit tests for handlers/help.py: role-filtered command list."""

import texts
from handlers.help import cmd_help
from storage import (
    MEMBER_APPROVED,
    MEMBER_PENDING,
    ROLE_GROUP_LEAD,
    ROLE_SUPERVISOR,
    Storage,
)
from tests.fakes import ADMIN_ID, _FakeMessage


async def _help_text(storage: Storage, user_id: int) -> str:
    message = _FakeMessage(from_user_id=user_id)
    await cmd_help(message, storage)
    return message.answers[0][0]


def _assert_contains(text: str, commands: list[str]) -> None:
    for command in commands:
        assert f"/{command}" in text


def _assert_excludes(text: str, commands: list[str]) -> None:
    for command in commands:
        assert f"/{command}" not in text


async def test_env_admin_sees_every_command(tmp_path):
    storage = Storage(tmp_path)
    text = await _help_text(storage, ADMIN_ID)

    assert texts.HELP_TITLE in text
    _assert_contains(
        text,
        ["start", "help", "cancel", "pending", "promote", "demote", "remove", "sethead"],
    )


async def test_approved_student_sees_student_commands(tmp_path):
    storage = Storage(tmp_path)
    await storage.upsert_member(111, "Студент Тестовий", "student", status=MEMBER_APPROVED)

    text = await _help_text(storage, 111)

    _assert_contains(text, ["start", "help", "cancel"])
    _assert_excludes(text, ["pending", "promote", "demote", "remove", "sethead"])


async def test_group_lead_sees_pending_but_not_admin(tmp_path):
    storage = Storage(tmp_path)
    await storage.upsert_member(111, "Лід Групи", "lead", status=MEMBER_APPROVED)
    await storage.add_role(111, ROLE_GROUP_LEAD)

    text = await _help_text(storage, 111)

    _assert_contains(text, ["start", "help", "cancel", "pending"])
    _assert_excludes(text, ["promote", "demote", "remove", "sethead"])


async def test_supervisor_sees_general_only(tmp_path):
    storage = Storage(tmp_path)
    await storage.upsert_member(111, "Супервайзер Тест", "sup", status=MEMBER_APPROVED)
    await storage.add_role(111, ROLE_SUPERVISOR)

    text = await _help_text(storage, 111)

    _assert_contains(text, ["start", "help", "cancel"])
    _assert_excludes(text, ["pending", "promote", "demote", "remove", "sethead"])


async def test_pending_member_sees_general_only(tmp_path):
    storage = Storage(tmp_path)
    await storage.upsert_member(111, "Студент Тестовий", "student", status=MEMBER_PENDING)

    text = await _help_text(storage, 111)

    _assert_contains(text, ["start", "help", "cancel"])
    _assert_excludes(text, ["pending", "promote", "demote", "remove", "sethead"])


async def test_unknown_user_sees_general_only(tmp_path):
    text = await _help_text(Storage(tmp_path), 111)

    _assert_contains(text, ["start", "help", "cancel"])
    _assert_excludes(text, ["pending", "promote", "demote", "remove", "sethead"])


async def test_removed_member_sees_general_only(tmp_path):
    storage = Storage(tmp_path)
    await storage.upsert_member(111, "Студент Тестовий", "student", status=MEMBER_APPROVED)
    await storage.add_role(111, ROLE_GROUP_LEAD)
    await storage.remove_member(111)

    text = await _help_text(storage, 111)

    _assert_contains(text, ["start", "help", "cancel"])
    _assert_excludes(text, ["pending", "promote", "demote", "remove", "sethead"])


async def test_pending_visibility_is_approval_aware(tmp_path):
    """/pending is visible only to env admins and approved group leads."""
    user_id = 111

    async def env_admin(storage: Storage) -> None:
        pass

    async def approved_group_lead(storage: Storage) -> None:
        await storage.upsert_member(user_id, "Лід Групи", "lead", status=MEMBER_APPROVED)
        await storage.add_role(user_id, ROLE_GROUP_LEAD)

    async def approved_student(storage: Storage) -> None:
        await storage.upsert_member(user_id, "Студент Тестовий", "student", status=MEMBER_APPROVED)

    async def approved_supervisor(storage: Storage) -> None:
        await storage.upsert_member(user_id, "Супервайзер Тест", "sup", status=MEMBER_APPROVED)
        await storage.add_role(user_id, ROLE_SUPERVISOR)

    async def pending_group_lead(storage: Storage) -> None:
        await storage.upsert_member(user_id, "Лід Групи", "lead", status=MEMBER_PENDING)
        await storage.add_role(user_id, ROLE_GROUP_LEAD)

    async def removed_group_lead(storage: Storage) -> None:
        await storage.upsert_member(user_id, "Лід Групи", "lead", status=MEMBER_APPROVED)
        await storage.add_role(user_id, ROLE_GROUP_LEAD)
        await storage.remove_member(user_id)

    cases = [
        ("env_admin", ADMIN_ID, env_admin, True),
        ("approved_group_lead", user_id, approved_group_lead, True),
        ("approved_student", user_id, approved_student, False),
        ("approved_supervisor", user_id, approved_supervisor, False),
        ("pending_group_lead", user_id, pending_group_lead, False),
        ("removed_group_lead", user_id, removed_group_lead, False),
    ]

    for name, current_user_id, setup, expected_visible in cases:
        storage = Storage(tmp_path / name)
        await setup(storage)
        text = await _help_text(storage, current_user_id)
        assert ("/pending" in text) == expected_visible, name
