"""Unit tests for handlers/report.py: report menu and the "today" report."""

from datetime import date

import texts
from handlers.report import open_reports, show_today_report
from storage import MEMBER_APPROVED, Storage
from tests.fakes import ADMIN_ID, _FakeCallback, _FakeMessage, _inline_button_texts


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
