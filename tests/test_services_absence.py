"""Tests for services/absence.py: days, reasons, confirmation summary, validation."""

from datetime import date
from zoneinfo import ZoneInfo

import pytest

from services.absence import (
    REASONS,
    build_absentees,
    build_days,
    build_success_text,
    classify_record,
    format_absentee_report,
    format_confirm,
    is_valid_reason,
    reason_brief,
    reason_display,
    validate_reason_text,
)

KYIV = ZoneInfo("Europe/Kyiv")


def test_build_days_normal_week():
    days = build_days(KYIV, date(2026, 9, 28))

    assert [day["day"] for day in days] == [
        date(2026, 9, 28),
        date(2026, 9, 29),
        date(2026, 9, 30),
    ]
    assert [day["label"] for day in days] == [
        "Сьогодні, 28.09 (пн)",
        "Завтра, 29.09 (вт)",
        "Післязавтра, 30.09 (ср)",
    ]


def test_build_days_crosses_year_boundary():
    days = build_days(KYIV, date(2026, 12, 31))

    assert [day["day"] for day in days] == [
        date(2026, 12, 31),
        date(2027, 1, 1),
        date(2027, 1, 2),
    ]
    assert [day["label"] for day in days] == [
        "Сьогодні, 31.12 (чт)",
        "Завтра, 01.01 (пт)",
        "Післязавтра, 02.01 (сб)",
    ]


def test_build_days_leap_february():
    days = build_days(KYIV, date(2024, 2, 28))

    assert [day["day"] for day in days] == [
        date(2024, 2, 28),
        date(2024, 2, 29),
        date(2024, 3, 1),
    ]
    assert [day["label"] for day in days] == [
        "Сьогодні, 28.02 (ср)",
        "Завтра, 29.02 (чт)",
        "Післязавтра, 01.03 (пт)",
    ]


def test_reasons_are_exactly_seven_unique_codes():
    codes = [code for code, _label in REASONS]

    assert len(REASONS) == 7
    assert len(set(codes)) == 7
    assert codes == [
        "illness",
        "family",
        "event",
        "transport",
        "academic",
        "excused",
        "other",
    ]


def test_format_confirm_has_new_replaced_identical():
    existing = {
        "2026-09-30": {"user_id": 1, "date": "2026-09-30", "reason": "family", "reason_text": None},
        "2026-10-01": {
            "user_id": 1,
            "date": "2026-10-01",
            "reason": "illness",
            "reason_text": None,
        },
    }

    text = format_confirm(
        [date(2026, 9, 29), date(2026, 9, 30), date(2026, 10, 1)],
        "illness",
        None,
        existing,
    )

    assert text.splitlines() == [
        "📅 29.09.2026 (вт)",
        "🔄 30.09.2026 (ср) — замінить «сімейні обставини»",
        "✅ 01.10.2026 (чт) — вже так",
        "💊 Причина: хвороба",
    ]


def test_format_confirm_other_reason_uses_free_text():
    text = format_confirm([date(2026, 9, 29)], "other", "захворів кіт", {})

    assert text.splitlines() == ["📅 29.09.2026 (вт)", "✍️ Інше: захворів кіт"]


def test_classify_record():
    same = {"reason": "illness", "reason_text": None}
    other = {"reason": "family", "reason_text": None}

    assert classify_record(None, "illness", None) == "created"
    assert classify_record(same, "illness", None) == "identical"
    assert classify_record(other, "illness", None) == "replaced"
    assert classify_record({"reason": "other", "reason_text": "пробки"}, "other", "пробки") == (
        "identical"
    )


def test_reason_display():
    assert reason_display("illness") == "хвороба"
    assert reason_display("excused") == "з дозволу"
    assert reason_display("other", "пробки на мосту") == "пробки на мосту"


def test_validate_reason_text_empty_raises():
    with pytest.raises(ValueError):
        validate_reason_text("")

    with pytest.raises(ValueError):
        validate_reason_text("   ")


def test_validate_reason_text_exactly_120_kept():
    text = "а" * 120

    assert validate_reason_text(text) == text


def test_validate_reason_text_121_raises():
    with pytest.raises(ValueError):
        validate_reason_text("х" * 121)


def test_validate_reason_text_strips_padding():
    assert validate_reason_text("  пробки  ") == "пробки"


def test_is_valid_reason_accepts_codes_declines_back():
    for code, _label in REASONS:
        assert is_valid_reason(code) is True
    assert is_valid_reason("back") is False
    assert is_valid_reason("bogus") is False


def test_build_success_text():
    text = build_success_text([date(2026, 9, 29), date(2026, 9, 30)], "хвороба")

    assert text.startswith("✅ Позначено: 29.09, 30.09 — хвороба")
    assert "запис заміниться" in text


# --- reports (selections) ---


def test_reason_brief_known_codes():
    assert reason_brief("illness") == "💊 хвороба"
    assert reason_brief("academic") == "🎓 справи коледжу"
    assert reason_brief("event") == "🏆 тренування/змагання"


def test_reason_brief_other_with_text():
    assert reason_brief("other", "пробки на мосту") == "✍️ Інше: пробки на мосту"


def test_reason_brief_other_empty():
    assert reason_brief("other") == "✍️ Інше: "


def test_build_absentees_joins_and_sorts_by_name():
    members = [
        (2, {"display_name": "Петренко Іван"}),
        (1, {"display_name": "бондаренко Петро"}),  # lowercase proves casefold is applied
        (3, {"display_name": "Сидоренко Марія"}),
    ]
    records = [
        (3, {"user_id": 3, "reason": "event", "reason_text": None}),
        (1, {"user_id": 1, "reason": "illness", "reason_text": None}),
        (2, {"user_id": 2, "reason": "other", "reason_text": "пробки на мосту"}),
    ]

    absentees = build_absentees(members, records)

    assert [member["display_name"] for member, _ in absentees] == [
        "бондаренко Петро",
        "Петренко Іван",
        "Сидоренко Марія",
    ]


def test_build_absentees_ignores_unknown_user_id():
    members = [(1, {"display_name": "Іваненко Петро"})]
    records = [
        (1, {"user_id": 1, "reason": "illness", "reason_text": None}),
        (99, {"user_id": 99, "reason": "illness", "reason_text": None}),
    ]

    absentees = build_absentees(members, records)

    assert len(absentees) == 1
    assert absentees[0][1]["user_id"] == 1


def test_build_absentees_empty():
    assert build_absentees([], []) == []


def test_format_absentee_report_exact():
    absentees = [
        (
            {"display_name": "Іваненко Петро"},
            {"user_id": 1, "reason": "illness", "reason_text": None},
        ),
        (
            {"display_name": "Петренко Іван"},
            {"user_id": 2, "reason": "other", "reason_text": "пробки на мосту"},
        ),
        (
            {"display_name": "Сидоренко Марія"},
            {"user_id": 3, "reason": "event", "reason_text": None},
        ),
    ]

    text = format_absentee_report(date(2026, 10, 3), absentees)

    assert text.splitlines() == [
        "📊 Відсутні на 03.10.2026 (сб):",
        "• Іваненко Петро — 💊 хвороба",
        "• Петренко Іван — ✍️ Інше: пробки на мосту",
        "• Сидоренко Марія — 🏆 тренування/змагання",
    ]


def test_format_absentee_report_empty():
    assert format_absentee_report(date(2026, 10, 3), []) == "✅ Сьогодні відсутніх немає"
