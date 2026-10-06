"""Unit tests for handlers/report.py: report menu and the "today" report."""

from datetime import date

import texts
from handlers.report import TELEGRAM_TEXT_MAX, open_reports, show_today_report
from services.absence import REASON_TEXT_MAX, build_absentees, format_absentee_report
from storage import MEMBER_APPROVED, Storage
from tests.fakes import ADMIN_ID, _FakeCallback, _FakeMessage, _inline_button_texts


class _EditOnlyMessage:
    def __init__(self) -> None:
        self.edits: list[tuple[str, object]] = []

    async def edit_text(self, text: str, reply_markup=None) -> None:
        self.edits.append((text, reply_markup))


async def test_open_reports_denied_for_student(tmp_path):
    storage = Storage(tmp_path)
    await storage.upsert_member(111, "Студент Тестовий", "student", status=MEMBER_APPROVED)

    msg = _FakeMessage(from_user_id=111)
    await open_reports(msg, storage)

    assert any(texts.NOT_ALLOWED_REPORTS in text for text, _ in msg.answers)


async def test_open_reports_allowed_for_group_lead(tmp_path):
    storage = Storage(tmp_path)
    await storage.upsert_member(111, "Лід Групи", "lead", status=MEMBER_APPROVED)
    await storage.add_role(111, "group_lead")

    msg = _FakeMessage(from_user_id=111)
    await open_reports(msg, storage)

    text, markup = msg.answers[0]
    assert text == texts.REPORT_PROMPT
    assert markup is not None
    assert _inline_button_texts(markup) == [texts.REPORT_TODAY_BUTTON]


async def test_open_reports_allowed_for_admin(tmp_path):
    storage = Storage(tmp_path)

    msg = _FakeMessage(from_user_id=ADMIN_ID)
    await open_reports(msg, storage)

    assert any(text == texts.REPORT_PROMPT for text, _ in msg.answers)


async def test_show_today_report_lists_absentees(tmp_path, monkeypatch):
    monkeypatch.setattr("handlers.report.current_day", lambda: date(2026, 10, 3))
    storage = Storage(tmp_path)
    await storage.upsert_member(111, "Лід Групи", "lead", status=MEMBER_APPROVED)
    await storage.add_role(111, "group_lead")
    await storage.upsert_member(1, "Іваненко Петро", "ivan", status=MEMBER_APPROVED)
    await storage.upsert_member(2, "Петренко Іван", "petro", status=MEMBER_APPROVED)
    await storage.upsert_absences_batch(1, ["2026-10-03"], "illness", None)
    await storage.upsert_absences_batch(2, ["2026-10-03"], "other", "пробки на мосту")

    callback = _FakeCallback(user_id=111)
    await show_today_report(callback, storage)

    text, _ = callback.message.edits[0]
    assert "📊 Відсутні на 03.10.2026 (сб):" in text
    assert "• Іваненко Петро — 💊 хвороба" in text
    assert "• Петренко Іван — ✍️ Інше: пробки на мосту" in text


async def test_show_today_report_empty(tmp_path, monkeypatch):
    monkeypatch.setattr("handlers.report.current_day", lambda: date(2026, 10, 3))
    storage = Storage(tmp_path)
    await storage.upsert_member(111, "Лід Групи", "lead", status=MEMBER_APPROVED)
    await storage.add_role(111, "group_lead")

    callback = _FakeCallback(user_id=111)
    await show_today_report(callback, storage)

    text, _ = callback.message.edits[0]
    assert text == texts.REPORT_TODAY_EMPTY


async def test_show_today_report_denied_for_revoked_rights(tmp_path, monkeypatch):
    monkeypatch.setattr("handlers.report.current_day", lambda: date(2026, 10, 3))
    storage = Storage(tmp_path)
    await storage.upsert_member(111, "Студент Тестовий", "student", status=MEMBER_APPROVED)

    callback = _FakeCallback(user_id=111)
    await show_today_report(callback, storage)

    assert callback.answers[0] == ((texts.NOT_ALLOWED_REPORTS,), {"show_alert": True})
    assert callback.message.edits == []


async def test_show_today_report_without_editable_message(tmp_path, monkeypatch):
    monkeypatch.setattr("handlers.report.current_day", lambda: date(2026, 10, 3))
    storage = Storage(tmp_path)
    await storage.upsert_member(111, "Лід Групи", "lead", status=MEMBER_APPROVED)
    await storage.add_role(111, "group_lead")

    callback = _FakeCallback(user_id=111)
    callback.message = object()
    await show_today_report(callback, storage)

    assert callback.answers == [((), {})]


async def test_show_today_report_with_edit_text_only(tmp_path, monkeypatch):
    monkeypatch.setattr("handlers.report.current_day", lambda: date(2026, 10, 3))
    storage = Storage(tmp_path)
    await storage.upsert_member(111, "Лід Групи", "lead", status=MEMBER_APPROVED)
    await storage.add_role(111, "group_lead")

    callback = _FakeCallback(user_id=111)
    message = _EditOnlyMessage()
    callback.message = message
    await show_today_report(callback, storage)

    assert message.edits == [(texts.REPORT_TODAY_EMPTY, None)]
    assert callback.answers == [((), {})]


async def test_show_today_report_splits_long_report(tmp_path, monkeypatch):
    monkeypatch.setattr("handlers.report.current_day", lambda: date(2026, 10, 3))
    storage = Storage(tmp_path)
    await storage.upsert_member(111, "Лід Групи", "lead", status=MEMBER_APPROVED)
    await storage.add_role(111, "group_lead")
    long_reason = "я" * REASON_TEXT_MAX
    for index in range(25):
        user_id = 1000 + index
        await storage.upsert_member(
            user_id, f"Студент {index:02d}", f"user{index}", status=MEMBER_APPROVED
        )
        await storage.upsert_absences_batch(user_id, ["2026-10-03"], "other", long_reason)

    callback = _FakeCallback(user_id=111)
    await show_today_report(callback, storage)

    first = callback.message.edits[0][0]
    assert isinstance(first, str)
    rest = [text for text, _ in callback.message.answers]
    chunks = [first, *rest]
    assert len(chunks) > 1
    assert all(len(chunk) <= TELEGRAM_TEXT_MAX for chunk in chunks)
    full_report = "\n".join(chunks)
    assert len(full_report) > 4096

    members = await storage.list_members(status=MEMBER_APPROVED)
    records = await storage.list_absences_for_date("2026-10-03")
    expected = format_absentee_report(date(2026, 10, 3), build_absentees(members, records))
    assert full_report == expected

    bullet_lines = [line for line in full_report.split("\n") if line.startswith("• ")]
    assert bullet_lines
    for line in bullet_lines:
        assert sum(line in chunk.split("\n") for chunk in chunks) == 1


def test_telegram_text_max_is_4096():
    assert TELEGRAM_TEXT_MAX == 4096
