"""Pure /help catalog: the command inventory and role-filtered rendering.

No aiogram — the module is covered by tests directly. Visibility is decided by
the services.members rights predicates, never by hardcoded roles. The drift
test (tests/test_help_catalog.py) uses `ast` to collect real handler commands.
"""

from typing import Callable, NamedTuple

import texts
from services.members import is_active_group_lead

# Audience codes: which rights predicate decides visibility of a command.
AUDIENCE_ALL = "all"
AUDIENCE_MANAGER = "manager"
AUDIENCE_ADMIN = "admin"


class HelpCommand(NamedTuple):
    command: str
    description: str
    audience: str


# Single source of truth: the command names here must match the real handlers
# (tests/test_help_catalog.py ast-parses handlers/*.py for Command("...")).
HELP_COMMANDS: list[HelpCommand] = [
    HelpCommand("start", texts.HELP_CMD_START, AUDIENCE_ALL),
    HelpCommand("help", texts.HELP_CMD_HELP, AUDIENCE_ALL),
    HelpCommand("cancel", texts.HELP_CMD_CANCEL, AUDIENCE_ALL),
    HelpCommand("pending", texts.HELP_CMD_PENDING, AUDIENCE_MANAGER),
    HelpCommand("promote", texts.HELP_CMD_PROMOTE, AUDIENCE_ADMIN),
    HelpCommand("demote", texts.HELP_CMD_DEMOTE, AUDIENCE_ADMIN),
    HelpCommand("remove", texts.HELP_CMD_REMOVE, AUDIENCE_ADMIN),
    HelpCommand("sethead", texts.HELP_CMD_SETHEAD, AUDIENCE_ADMIN),
]


def open_commands() -> list[HelpCommand]:
    """Catalog entries open to everyone, in catalog order (Telegram menu)."""
    return [entry for entry in HELP_COMMANDS if entry.audience == AUDIENCE_ALL]


# Commands open to everyone (AUDIENCE_ALL), derived from the catalog so the ACL
# and the /help visibility cannot drift apart.
OPEN_COMMANDS: frozenset[str] = frozenset(entry.command for entry in open_commands())

# Visibility per audience. Each predicate takes the roster entry and the
# already-resolved env-admin flag, and uses only the services.members predicates.
_PREDICATES: dict[str, Callable[[dict | None, bool], bool]] = {
    AUDIENCE_ALL: lambda member, is_admin: True,
    AUDIENCE_MANAGER: lambda member, is_admin: is_admin or is_active_group_lead(member),
    AUDIENCE_ADMIN: lambda member, is_admin: is_admin,
}


def visible_commands(member: dict | None, is_admin: bool) -> list[HelpCommand]:
    """Commands the caller may use, in catalog order."""
    return [
        command
        for command in HELP_COMMANDS
        if _PREDICATES[command.audience](member, is_admin)
    ]


def build_help_text(member: dict | None, is_admin: bool) -> str:
    """Role-filtered /help message: a title, a blank line, then one command per line.

    Commands are listed in catalog order, each rendered with texts.HELP_LINE.
    """
    commands = visible_commands(member, is_admin)
    lines = [texts.HELP_TITLE, ""]
    for command in commands:
        lines.append(
            texts.HELP_LINE.format(command=command.command, description=command.description)
        )
    return "\n".join(lines)
