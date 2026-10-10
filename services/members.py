"""Pure logic of roles/onboarding: full-name validation, rights, labels.

No aiogram — covered by tests directly.
"""

from typing import Any

from storage import MEMBER_APPROVED, ROLE_GROUP_LEAD, ROLE_SUPERVISOR, ROLES

# ASCII apostrophe and the typographic one (U+2019) are both common in Ukrainian names.
_NAME_ALLOWED = "-'’"

# Hard cap for a normalized full name (two words together).
NAME_MAX_LEN = 60

_ROLE_NAMES = {ROLE_GROUP_LEAD: "староста", ROLE_SUPERVISOR: "супервайзер"}


def validate_full_name(text: str) -> str:
    """Strict "Surname Name" validation: exactly 2 words, letters/hyphen/apostrophe,
    at most NAME_MAX_LEN characters.

    Valid examples: Ukrainian two-word names (with hyphen/apostrophe allowed).
    Invalid: one word, three words, digits, empty/symbol words, too long names.
    Returns the normalized string (single spaces).
    """
    cleaned = " ".join((text or "").split())
    words = cleaned.split(" ")
    if len(words) != 2:
        raise ValueError("full name must be exactly two words")
    if len(cleaned) > NAME_MAX_LEN:
        raise ValueError("full name is too long")
    for word in words:
        if len(word) < 2:
            raise ValueError("word is too short")
        if not any(ch.isalpha() for ch in word):
            raise ValueError("word has no letters")
        if not all(ch.isalpha() or ch in _NAME_ALLOWED for ch in word):
            raise ValueError("word has unsupported characters")
    return cleaned


def is_admin(user_id: int, admin_ids: set[int] | frozenset[int] | list[int] | None = None) -> bool:
    """Env admin? (bootstrap list from config.ADMIN_USER_IDS)."""
    if admin_ids is None:
        from config import ADMIN_USER_IDS

        admin_ids = ADMIN_USER_IDS
    return user_id in admin_ids


def has_role(member: dict | None, role: str) -> bool:
    """Whether the roster entry has the given role."""
    if not isinstance(member, dict):
        return False
    roles = member.get("roles")
    return isinstance(roles, list) and role in roles


def is_approved(member: dict | None) -> bool:
    """Whether the roster entry is in the approved status."""
    return isinstance(member, dict) and member.get("status") == MEMBER_APPROVED


def has_any_role(member: dict | None) -> bool:
    """Whether the roster entry has at least one role."""
    if not isinstance(member, dict):
        return False
    roles = member.get("roles")
    return isinstance(roles, list) and len(roles) > 0


def is_valid_role(role: str | None) -> bool:
    """Whether the role is a known assignable role."""
    return role in ROLES


def member_label(member: dict) -> str:
    """«Full Name (@ivan)» — for cards and button lists."""
    username = member.get("username")
    if username:
        return f"{member.get('display_name', '?')} (@{username})"
    return member.get("display_name", "?")


def can_manage(member: dict | None) -> bool:
    """Whether the roster entry holds the group_lead role."""
    return has_role(member, ROLE_GROUP_LEAD)


def can_process_requests(member: dict | None, is_admin: bool) -> bool:
    """Who may process join requests: env admin or a group_lead."""
    return is_admin or can_manage(member)


def is_active_group_lead(member: dict | None) -> bool:
    """Whether the roster entry can receive request cards (approved group_lead)."""
    return is_approved(member) and can_manage(member)


def can_mark_absence(member: dict | None, is_admin: bool) -> bool:
    """Who may mark absence: env admin, or an approved non-supervisor member."""
    if is_admin:
        return True
    if not isinstance(member, dict):
        return False
    if not is_approved(member):
        return False
    return not has_role(member, ROLE_SUPERVISOR)


def can_view_reports(member: dict | None, is_admin: bool) -> bool:
    """Who may open reports/selections: env admin, group_lead or supervisor.

    Role predicates such as this one assume an already-admitted (approved)
    member: AccessControlMiddleware is the approval gate, and approval-awareness
    lives only in predicates used to build selectable lists before admission
    (e.g. is_active_group_lead).
    """
    if is_admin:
        return True
    if not isinstance(member, dict):
        return False
    return has_role(member, ROLE_GROUP_LEAD) or has_role(member, ROLE_SUPERVISOR)


def can_send_notifications(member: dict | None, is_admin: bool) -> bool:
    """Who may broadcast a notification: delegated to can_view_reports for now."""
    return can_view_reports(member, is_admin)


def role_name(role: str) -> str:
    """Human-readable role name for messages (localized)."""
    return _ROLE_NAMES.get(role, role)


def synthetic_member(roles: list[str]) -> dict[str, Any]:
    """Approved roster entry shape for keyboard building (no persistence)."""
    return {"status": MEMBER_APPROVED, "roles": list(roles)}
