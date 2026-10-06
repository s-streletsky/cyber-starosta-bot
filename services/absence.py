"""Pure logic of the "I will be absent" flow: days, reasons, confirmation summary.

No aiogram — the module is covered by tests directly.
"""

from datetime import date, datetime, timedelta
from typing import Any, Literal
from zoneinfo import ZoneInfo

import texts
from storage import (
    ABSENCE_ATTEMPT_LIMIT,
    ABSENCE_CREATED,
    ABSENCE_IDENTICAL,
    ABSENCE_REPLACED,
    AbsentStatus,
    is_identical_absence,
)

# Code of the free-text reason; compared in handlers and in this module.
REASON_OTHER = "other"

# 7 reasons: order and emoji match the keyboard.
REASONS: list[tuple[str, str]] = [
    ("illness", "💊 Хвороба"),
    ("family", "🏠 Сімейні обставини"),
    ("event", "🏆 Тренування/Змагання"),
    ("transport", "🚇 Затори"),
    ("academic", "🎓 Справи коледжу"),
    ("excused", "📋 З дозволу"),
    (REASON_OTHER, "✍️ Інше…"),
]

REASON_TEXT_MAX = 250

_REASON_LABELS = dict(REASONS)
_WEEKDAYS = ("пн", "вт", "ср", "чт", "пт", "сб", "вс")
_DAY_PREFIXES = ("Сьогодні", "Завтра", "Післязавтра")


def weekday_short(day: date) -> str:
    """Short local weekday (2-letter abbreviation)."""
    return _WEEKDAYS[day.weekday()]


def format_date_short(day: date) -> str:
    """28.09"""
    return day.strftime("%d.%m")


def format_date_full(day: date) -> str:
    """29.09.2026"""
    return day.strftime("%d.%m.%Y")


def format_dates_short(days: list[date]) -> str:
    """29.09, 30.09"""
    return ", ".join(format_date_short(day) for day in days)


def build_days(
    tz_zone: ZoneInfo, today: date | None = None
) -> list[dict[str, Any]]:
    """Three consecutive days: today, tomorrow, the day after tomorrow.

    If today is not provided, the current date in tz_zone is used (at render time).
    Each item: {"day": date, "label": "<prefix>, 28.09 (<weekday>)"}.
    """
    if today is None:
        today = datetime.now(tz_zone).date()

    days: list[dict[str, Any]] = []
    for offset, prefix in enumerate(_DAY_PREFIXES):
        day = today + timedelta(days=offset)
        days.append(
            {"day": day, "label": f"{prefix}, {format_date_short(day)} ({weekday_short(day)})"}
        )
    return days


def reason_display(reason_code: str, reason_text: str | None = None) -> str:
    """Reason for messages: «illness» by code, free text for other."""
    if reason_code == REASON_OTHER:
        text = (reason_text or "").strip()
        if text:
            return text
        return ""
    label = _REASON_LABELS.get(reason_code, reason_code)
    name = label.partition(" ")[2]
    return (name or label).lower()


def classify_record(
    record: dict[str, Any] | None, reason_code: str, reason_text: str | None
) -> AbsentStatus:
    """created — there was no record; identical — same reason; replaced — will be replaced."""
    if record is None:
        return ABSENCE_CREATED
    if is_identical_absence(record, reason_code, reason_text):
        return ABSENCE_IDENTICAL
    return ABSENCE_REPLACED


def _reason_line(reason_code: str, reason_text: str | None) -> str:
    if reason_code == REASON_OTHER:
        return texts.CONFIRM_OTHER_REASON.format(text=reason_text or "")
    emoji = _REASON_LABELS.get(reason_code, reason_code).partition(" ")[0]
    return texts.CONFIRM_REASON.format(emoji=emoji, name=reason_display(reason_code))


def format_confirm(
    records: list[date],
    reason_code: str,
    reason_text: str | None,
    existing_index: dict[str, dict[str, Any]],
) -> str:
    """Confirmation step summary: one line per date + a reason line.

    records — selected dates; existing_index — the user's already existing records
    in the format {"YYYY-MM-DD": record}.
    """
    lines: list[str] = []
    for day in sorted(records):
        existing = existing_index.get(day.isoformat())
        status = classify_record(existing, reason_code, reason_text)
        date_full = format_date_full(day)
        weekday = weekday_short(day)
        if status == ABSENCE_CREATED:
            lines.append(texts.CONFIRM_NEW_LINE.format(date=date_full, weekday=weekday))
        elif status == ABSENCE_IDENTICAL:
            lines.append(texts.CONFIRM_IDENTICAL_LINE.format(date=date_full, weekday=weekday))
        else:
            old = existing or {}
            old_reason = reason_display(old.get("reason", ""), old.get("reason_text"))
            lines.append(
                texts.CONFIRM_REPLACED_LINE.format(
                    date=date_full, weekday=weekday, old_reason=old_reason
                )
            )
    lines.append(_reason_line(reason_code, reason_text))
    return "\n".join(lines)


class ReasonTextError(ValueError):
    """Empty or too-long free-text reason; `kind` selects the user-facing message."""

    def __init__(self, kind: Literal["empty", "too_long"]) -> None:
        super().__init__(kind)
        self.kind = kind


def validate_reason_text(text: str) -> str:
    """Strip; ReasonTextError if empty or longer than REASON_TEXT_MAX characters."""
    cleaned = (text or "").strip()
    if not cleaned:
        raise ReasonTextError("empty")
    if len(cleaned) > REASON_TEXT_MAX:
        raise ReasonTextError("too_long")
    return cleaned


def is_valid_reason(code: str) -> bool:
    """Whether the code belongs to the reason keyboard (REASONS)."""
    return code in _REASON_LABELS


def build_success_text(dates: list[date], reason_label: str) -> str:
    """Step 4 text after writing to storage."""
    return texts.SUCCESS.format(dates=format_dates_short(dates), reason=reason_label)


# --- logical deletion (tombstones) ---


def is_deletable_day(day: date, today: date) -> bool:
    """Only today and later are deletable; strictly past days are not."""
    return day >= today


def format_delete_confirm(days: list[date]) -> str:
    """Deletion confirmation: one line per date (sorted) + the question, no reason."""
    lines = [
        texts.DELETE_CONFIRM_LINE.format(date=format_date_full(day), weekday=weekday_short(day))
        for day in sorted(days)
    ]
    lines.append(texts.DELETE_QUESTION)
    return "\n".join(lines)


def format_delete_result(deleted: list[date]) -> str:
    """Success text with the deleted dates, or a notice when nothing was deleted."""
    if not deleted:
        return texts.DELETE_NOTHING
    return texts.DELETE_SUCCESS.format(dates=format_dates_short(sorted(deleted)))


# --- per-date mutation attempt limit ---


def is_within_attempt_limit(used: int) -> bool:
    """Whether one more mutation is allowed for a date with `used` attempts."""
    return used < ABSENCE_ATTEMPT_LIMIT


def format_limit_reached(dates: list[date]) -> str:
    """Notice when every selected date has exhausted its mutation limit."""
    return texts.LIMIT_REACHED.format(
        limit=ABSENCE_ATTEMPT_LIMIT, dates=format_dates_short(sorted(dates))
    )


def format_limit_partial(blocked: list[date]) -> str:
    """Notice when only some selected dates have exhausted their mutation limit."""
    return texts.LIMIT_REACHED_PARTIAL.format(
        limit=ABSENCE_ATTEMPT_LIMIT, dates=format_dates_short(sorted(blocked))
    )


# --- reports (selections) ---


def reason_brief(reason_code: str, reason_text: str | None = None) -> str:
    """Short reason for a report line: «💊 хвороба» or «✍️ Інше: <text>»."""
    if reason_code == REASON_OTHER:
        return texts.CONFIRM_OTHER_REASON.format(text=reason_text or "")
    emoji = _REASON_LABELS.get(reason_code, reason_code).partition(" ")[0]
    return f"{emoji} {reason_display(reason_code)}"


def build_absentees(
    members: list[tuple[int, dict[str, Any]]],
    records: list[tuple[int, dict[str, Any]]],
) -> list[tuple[dict[str, Any], dict[str, Any]]]:
    """Joins records with members, ordered by display name then user_id.

    Records whose user_id has no member are ignored. The ordering is
    case-insensitive and deterministic for stable report output.
    """
    member_by_id = {user_id: member for user_id, member in members}
    absentees = [
        (member_by_id[user_id], record)
        for user_id, record in records
        if user_id in member_by_id
    ]
    absentees.sort(
        key=lambda pair: (
            (pair[0].get("display_name") or "").casefold(),
            pair[1]["user_id"],
        )
    )
    return absentees


def format_absentee_report(
    day: date, absentees: list[tuple[dict[str, Any], dict[str, Any]]]
) -> str:
    """One day's report: a header plus one line per absentee, or an empty notice."""
    if not absentees:
        return texts.REPORT_TODAY_EMPTY
    lines = [
        texts.REPORT_TODAY_HEADER.format(date=format_date_full(day), weekday=weekday_short(day))
    ]
    for member, record in absentees:
        lines.append(
            texts.REPORT_LINE.format(
                name=member.get("display_name") or "?",
                reason=reason_brief(record.get("reason", ""), record.get("reason_text")),
            )
        )
    return "\n".join(lines)
