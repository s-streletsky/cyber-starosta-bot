"""S1: server-side role ACL predicates."""

from services.members import can_mark_absence, can_view_reports


def _member(status: str, roles: list[str]) -> dict:
    return {"display_name": "Петренко Іван", "username": "ivan", "status": status, "roles": roles}


def test_can_mark_absence_student_and_lead():
    assert can_mark_absence(_member("approved", []), is_admin=False) is True
    assert can_mark_absence(_member("approved", ["group_lead"]), is_admin=False) is True


def test_can_mark_absence_denies_supervisor_and_pending():
    assert can_mark_absence(_member("approved", ["supervisor"]), is_admin=False) is False
    assert can_mark_absence(_member("pending", []), is_admin=False) is False
    assert can_mark_absence(None, is_admin=False) is False


def test_can_mark_absence_allows_admin():
    assert can_mark_absence(None, is_admin=True) is True


def test_can_view_reports_lead_supervisor_admin():
    assert can_view_reports(_member("approved", ["group_lead"]), is_admin=False) is True
    assert can_view_reports(_member("approved", ["supervisor"]), is_admin=False) is True
    assert can_view_reports(None, is_admin=True) is True


def test_can_view_reports_denies_student():
    assert can_view_reports(_member("approved", []), is_admin=False) is False
    assert can_view_reports(None, is_admin=False) is False
