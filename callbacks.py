"""CallbackData factories: handlers contain no string callback_data.

Action codes are defined here as constants; keyboards and handlers must use
these names, never raw strings. The Literal field annotations mirror the
constants (mypy cannot interpolate named constants into Literal, so the
strings are written inline — keep them in sync with the constants above).
"""

from typing import Final, Literal

from aiogram.filters.callback_data import CallbackData

# --- ApproveCb.action ---
APPROVE_ACCEPT: Final = "accept"
APPROVE_REJECT: Final = "reject"

# --- AdminCb.action ---
ADMIN_PICK_PROMOTE: Final = "pick_promote"
ADMIN_SET_ROLE: Final = "set_role"
ADMIN_DEMOTE: Final = "demote"
ADMIN_REMOVE: Final = "remove"
ADMIN_SET_HEAD: Final = "sethead"

# --- ReportCb.action ---
REPORT_TODAY: Final = "today"

# --- shared action values: ACTION_BACK (ReasonCb.code, ConfirmCb.action);
# ACTION_NEXT / ACTION_CANCEL (DayCtl.action) ---
ACTION_NEXT: Final = "next"
ACTION_BACK: Final = "back"
ACTION_CANCEL: Final = "cancel"
ACTION_SEND: Final = "send"

AdminAction = Literal["pick_promote", "set_role", "demote", "remove", "sethead"]


class DayCb(CallbackData, prefix="d"):
    """Day selection: «d:2026-09-29»."""

    date: str


class DayCtl(CallbackData, prefix="dc"):
    """Date-step buttons: «dc:next» / «dc:cancel»."""

    action: Literal["next", "cancel"]


class ReasonCb(CallbackData, prefix="r"):
    """Reason selection: «r:illness» … «r:other», «r:back».

    code stays a plain str: reason codes come from services.absence.REASONS
    dynamically; only the back button uses ACTION_BACK.
    """

    code: str


class ConfirmCb(CallbackData, prefix="c"):
    """Confirmation buttons: «c:send» / «c:back»."""

    action: Literal["send", "back"]


class ApproveCb(CallbackData, prefix="ar"):
    """Request card: «ar:accept:123» / «ar:reject:123»."""

    action: Literal["accept", "reject"]
    user_id: int


class AdminCb(CallbackData, prefix="adm"):
    """Admin lists: picking a person and actions with role/removal/lead.

    role: "group_lead" | "supervisor" | None (None — role choice step;
          aiogram turns an empty segment into None, hence the str | None type)
    """

    action: AdminAction
    user_id: int
    role: str | None = None


class ReportCb(CallbackData, prefix="rep"):
    """Report selection: «rep:today»."""

    action: Literal["today"]
