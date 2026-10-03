"""Data storage: JSONL with append-only absence records + atomic roster upsert.

One instance per process: created in bot.main() and passed to handlers
via dp.workflow_data["storage"].
"""

import asyncio
import json
import logging
import os
import shutil
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Literal

logger = logging.getLogger(__name__)

AbsentStatus = Literal["created", "replaced", "identical", "deleted", "limit"]
MemberStatus = Literal["created", "updated"]
MemberState = Literal["approved", "pending", "removed"]
PendingResult = Literal["approved", "rejected", "not_pending", "missing"]
ReadState = Literal["missing", "ok", "corrupt"]

ROLE_GROUP_LEAD = "group_lead"
ROLE_SUPERVISOR = "supervisor"
ROLES = (ROLE_GROUP_LEAD, ROLE_SUPERVISOR)

MEMBER_APPROVED: MemberState = "approved"
MEMBER_PENDING: MemberState = "pending"
MEMBER_REMOVED: MemberState = "removed"

RESULT_APPROVED: PendingResult = "approved"
RESULT_REJECTED: PendingResult = "rejected"
RESULT_NOT_PENDING: PendingResult = "not_pending"
RESULT_MISSING: PendingResult = "missing"

UPSERT_CREATED: MemberStatus = "created"
UPSERT_UPDATED: MemberStatus = "updated"

ABSENCE_CREATED: AbsentStatus = "created"
ABSENCE_REPLACED: AbsentStatus = "replaced"
ABSENCE_IDENTICAL: AbsentStatus = "identical"
ABSENCE_DELETED: AbsentStatus = "deleted"
ABSENCE_LIMIT: AbsentStatus = "limit"

# Lifetime per-date mutation cap (ADD/REPLACE/DELETE): the counter is derived
# from the append-only journal, so old lines count and no extra file is needed.
ABSENCE_ATTEMPT_LIMIT = 10

# JSON dictionary files can be missing (normal first run), valid, or corrupt.
READ_MISSING: ReadState = "missing"
READ_OK: ReadState = "ok"
READ_CORRUPT: ReadState = "corrupt"


class StorageCorruptError(RuntimeError):
    """Raised when a write is attempted on a corrupt members file."""



def is_identical_absence(
    record: dict[str, Any] | None, reason: str, reason_text: str | None
) -> bool:
    """Whether an existing record already has this exact reason and text."""
    return (
        record is not None
        and record.get("reason") == reason
        and record.get("reason_text") == reason_text
    )


def is_deleted(record: dict[str, Any] | None) -> bool:
    """True when the record is a deletion tombstone (logical delete)."""
    return record is not None and record.get("deleted") is True


def _roles_of(member: dict[str, Any]) -> list[str]:
    """Ensures member["roles"] is a list and returns it (in place)."""
    roles = member.get("roles")
    if not isinstance(roles, list):
        roles = []
        member["roles"] = roles
    return roles


def _member_defaults(member: Any) -> dict[str, Any] | None:
    """Normalizes a roster entry: v1 entries without status/roles are treated
    as an approved student (no on-disk migration needed)."""
    if not isinstance(member, dict):
        return None
    member = dict(member)
    member.setdefault("status", MEMBER_APPROVED)
    if member["status"] not in (MEMBER_APPROVED, MEMBER_PENDING, MEMBER_REMOVED):
        member["status"] = MEMBER_APPROVED
    _roles_of(member)
    return member


class Storage:
    """Two files in DATA_DIR:

    - absences.jsonl — append-only journal; reader contract: the last line for a
      key (user_id, date) wins. Deletion is logical: a tombstone
      ({"deleted": True}) is appended for the key, so deleted keys read as absent
      (get_record → None) and are excluded from reports. Re-marking a deleted key
      appends a fresh active record;
    - members.json — roster dictionary v2 (display_name, username, status, roles),
      written atomically (temp + os.replace). The optional boolean `is_head_lead` marks
      the head group lead — the recipient of request cards; no field means not lead.
    """

    def __init__(self, data_dir: str | Path) -> None:
        self.data_dir = Path(data_dir)
        self.data_dir.mkdir(parents=True, exist_ok=True)
        self.absences_path = self.data_dir / "absences.jsonl"
        self.members_path = self.data_dir / "members.json"
        self._lock = asyncio.Lock()
        self._index: dict[tuple[int, str], dict[str, Any]] = {}
        self._attempts: dict[tuple[int, str], int] = {}
        self._load_absences()

    # ---------- reading ----------

    @staticmethod
    def _parse_line(line: str) -> dict[str, Any] | None:
        """Parses a journal line; broken lines are skipped with a warning.

        The line content is never logged: it may contain user text (PII).
        Only structural facts (length and error type) go to logs.
        """
        line = line.strip()
        if not line:
            return None
        try:
            record = json.loads(line)
        except json.JSONDecodeError as exc:
            logger.warning("Skipping broken absences line (len=%d, error=%s)", len(line), exc)
            return None
        if not isinstance(record, dict) or not isinstance(record.get("user_id"), int):
            logger.warning("Skipping absences line with unexpected structure (len=%d)", len(line))
            return None
        if not isinstance(record.get("date"), str):
            logger.warning("Skipping absences line without a date (len=%d)", len(line))
            return None
        return record

    def _load_absences(self) -> None:
        """Preloads the index; the last line for a key overwrites previous ones.

        Every parsed line also counts as one mutation attempt for its key —
        the counter is rebuilt from the whole journal on load (old lines count).
        """
        if not self.absences_path.exists():
            return
        with self.absences_path.open(encoding="utf-8") as file:
            for line in file:
                record = self._parse_line(line)
                if record is not None:
                    key = (record["user_id"], record["date"])
                    self._index[key] = record
                    self._attempts[key] = self._attempts.get(key, 0) + 1

    async def get_record(self, user_id: int, date: str) -> dict[str, Any] | None:
        """Last active record for a key or None (missing, or logically deleted)."""
        record = self._index.get((user_id, date))
        if record is None or is_deleted(record):
            return None
        return dict(record)

    async def list_absences_for_date(self, date: str) -> list[tuple[int, dict[str, Any]]]:
        """All journal records for one date as (user_id, record) copies.

        Reads the in-memory index only: no await points, no file I/O
        (mirrors the lock-free read invariant of get_record).
        """
        return [
            (user_id, dict(record))
            for (user_id, record_date), record in self._index.items()
            if record_date == date and not is_deleted(record)
        ]

    async def count_day_attempts(self, user_id: int, date: str) -> int:
        """Lifetime mutation attempts for one (user_id, date).

        Reads the in-memory counter only: no await points, no file I/O
        (mirrors the lock-free read invariant of get_record).
        """
        return self._attempts.get((user_id, date), 0)

    # ---------- absence writes ----------

    async def upsert_absences_batch(
        self,
        user_id: int,
        dates: list[str],
        reason: str,
        reason_text: str | None,
        enforce_limit: bool = True,
    ) -> list[AbsentStatus]:
        """Batch upsert absence records for a single lock acquisition.

        Appends all date records under a single lock acquisition. Each record is
        fsync'd individually, so a crash mid-batch may leave a partial journal —
        which is a valid state for an append-only log (last write wins per key).

        With enforce_limit, a key that already reached ABSENCE_ATTEMPT_LIMIT is
        skipped with ABSENCE_LIMIT (identical re-marks are checked first and
        consume nothing). Handlers pass enforce_limit=False for env admins.
        """
        async with self._lock:
            results: list[AbsentStatus] = []
            for date in dates:
                key = (user_id, date)
                existing = self._index.get(key)
                if is_deleted(existing):
                    existing = None
                if is_identical_absence(existing, reason, reason_text):
                    results.append(ABSENCE_IDENTICAL)
                    continue
                if enforce_limit and self._attempts.get(key, 0) >= ABSENCE_ATTEMPT_LIMIT:
                    results.append(ABSENCE_LIMIT)
                    continue

                record: dict[str, Any] = {
                    "user_id": user_id,
                    "date": date,
                    "reason": reason,
                    "reason_text": reason_text,
                    "created_at": datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ"),
                }
                self._append_line(record)
                self._index[key] = record
                self._attempts[key] = self._attempts.get(key, 0) + 1
                results.append(ABSENCE_CREATED if existing is None else ABSENCE_REPLACED)
            return results

    async def delete_absences_batch(
        self, user_id: int, dates: list[str], enforce_limit: bool = True
    ) -> list[AbsentStatus]:
        """Logical delete: append a tombstone per active record.

        A missing or already-deleted key is a no-op and reports ABSENCE_IDENTICAL,
        so repeated deletion is idempotent. Mirrors upsert_absences_batch: one lock
        acquisition, fsync per appended line, no await inside the critical section.

        With enforce_limit, an active key that already reached ABSENCE_ATTEMPT_LIMIT
        is skipped with ABSENCE_LIMIT (deletion consumes one attempt). Handlers pass
        enforce_limit=False for env admins.
        """
        async with self._lock:
            results: list[AbsentStatus] = []
            for date in dates:
                key = (user_id, date)
                existing = self._index.get(key)
                if existing is None or is_deleted(existing):
                    results.append(ABSENCE_IDENTICAL)
                    continue
                if enforce_limit and self._attempts.get(key, 0) >= ABSENCE_ATTEMPT_LIMIT:
                    results.append(ABSENCE_LIMIT)
                    continue

                tombstone: dict[str, Any] = {
                    "user_id": user_id,
                    "date": date,
                    "deleted": True,
                    "created_at": datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ"),
                }
                self._append_line(tombstone)
                self._index[key] = tombstone
                self._attempts[key] = self._attempts.get(key, 0) + 1
                results.append(ABSENCE_DELETED)
            return results

    def _append_line(self, record: dict[str, Any]) -> None:
        """Pure append: write + flush + fsync. Temp+replace is not needed here."""
        line = json.dumps(record, ensure_ascii=False)
        with self.absences_path.open("a", encoding="utf-8", newline="\n") as file:
            file.write(line + "\n")
            file.flush()
            os.fsync(file.fileno())

    # ---------- roster ----------

    def _read_members(self, strict: bool = False) -> dict[str, Any]:
        """members.json is always re-read from disk — external edits are not lost.

        strict=False (read paths): a corrupt file is logged and read as empty.
        strict=True (write paths): a corrupt file is snapshotted and raises
        StorageCorruptError before it can be overwritten.
        """
        return self._read_json_dict(self.members_path, "members", strict)

    def _read_json_dict(self, path: Path, name: str, strict: bool) -> dict[str, Any]:
        """Returns the parsed dictionary, applying the three read states."""
        state, payload = self._load_json_dict(path)
        if state == READ_OK:
            return payload
        if state == READ_CORRUPT:
            self._handle_corrupt(path, name, strict, payload)
        return {}

    @staticmethod
    def _load_json_dict(path: Path) -> tuple[ReadState, Any]:
        """Loads one JSON file:

        READ_MISSING — the file does not exist, payload is {};
        READ_OK      — payload is the parsed dictionary;
        READ_CORRUPT — payload is the reason (exception or message).
        """
        if not path.exists():
            return READ_MISSING, {}
        try:
            with path.open(encoding="utf-8") as file:
                data = json.load(file)
        except (json.JSONDecodeError, OSError) as exc:
            return READ_CORRUPT, exc
        if not isinstance(data, dict):
            return READ_CORRUPT, "top-level JSON is not an object"
        return READ_OK, data

    def _handle_corrupt(self, path: Path, name: str, strict: bool, reason: object) -> None:
        """Never silently overwrite a damaged file: snapshot it, then decide."""
        if not strict:
            logger.error("%s.json is corrupt (%s) — reading as empty", name, reason)
            return
        self._snapshot_corrupt(path, name)
        logger.critical("%s.json is corrupt (%s) — refusing to overwrite", name, reason)
        raise StorageCorruptError(f"{name}.json is corrupt")

    def _snapshot_corrupt(self, path: Path, name: str) -> None:
        """Best-effort copy of the damaged file; snapshot failures never raise.

        Only the first snapshot of a given file is kept: the original corrupt
        content never changes, so repeated write attempts must not pile up copies.
        """
        existing = list(self.data_dir.glob(f"{name}.corrupt-*.json"))
        if existing:
            logger.info(
                "%s is corrupt — keeping the existing snapshot %s",
                path.name,
                existing[0].name,
            )
            return
        timestamp = datetime.now(UTC).strftime("%Y%m%d-%H%M%S-%f")
        snapshot = self.data_dir / f"{name}.corrupt-{timestamp}.json"
        try:
            shutil.copy2(path, snapshot)
        except OSError:
            logger.warning("Failed to snapshot corrupt %s", path, exc_info=True)

    def _fsync_dir(self) -> None:
        """fsync the directory so a rename survives a crash.

        Some platforms (Windows) do not support directory fsync — skip silently.
        """
        try:
            dir_fd = os.open(self.data_dir, os.O_RDONLY)
            try:
                os.fsync(dir_fd)
            finally:
                os.close(dir_fd)
        except OSError:
            logger.debug("Directory fsync is not supported here", exc_info=True)

    def _write_members(self, members: dict[str, Any]) -> None:
        """Atomic write: temp file in the same directory + os.replace."""
        temp_path = self.members_path.with_name(self.members_path.name + ".tmp")
        with temp_path.open("w", encoding="utf-8", newline="\n") as file:
            json.dump(members, file, ensure_ascii=False, indent=2)
            file.write("\n")
            file.flush()
            os.fsync(file.fileno())
        os.replace(temp_path, self.members_path)
        self._fsync_dir()

    async def upsert_member(
        self,
        user_id: int,
        display_name: str,
        username: str | None,
        status: MemberState = MEMBER_PENDING,
    ) -> MemberStatus:
        """Roster entry upsert.

        For an existing key only username is updated: display_name, status and
        roles are not overwritten, so admin edits and the request flow do not reset.
        A new member is created with `status` (pending by default; env admins are
        created already approved).
        """
        async with self._lock:
            members = self._read_members(strict=True)
            key = str(user_id)
            current = _member_defaults(members.get(key))
            if current is not None:
                if current.get("username") == username:
                    return UPSERT_UPDATED
                current["username"] = username
                members[key] = current
                result: MemberStatus = UPSERT_UPDATED
            else:
                members[key] = {
                    "display_name": display_name,
                    "username": username,
                    "status": status,
                    "roles": [],
                }
                result = UPSERT_CREATED
            self._write_members(members)
            return result

    async def get_member(self, user_id: int) -> dict[str, Any] | None:
        """Roster entry or None if the user does not exist yet."""
        member = _member_defaults(self._read_members().get(str(user_id)))
        return member

    async def resubmit_member(self, user_id: int, display_name: str, username: str | None) -> None:
        """Resubmission (after reject or removed): the full name is overwritten,
        status → pending. Roles are kept — removal already cleared them.
        The head-lead flag is dropped: a pending member can never be the head lead."""
        async with self._lock:
            members = self._read_members(strict=True)
            key = str(user_id)
            current = members.get(key)
            if not isinstance(current, dict):
                current = {}
            current["display_name"] = display_name
            current["username"] = username
            current["status"] = MEMBER_PENDING
            _roles_of(current)
            current.pop("is_head_lead", None)
            members[key] = current
            self._write_members(members)

    async def approve_pending(self, user_id: int) -> PendingResult:
        """pending → approved, atomically. Removed is NOT touched here."""
        async with self._lock:
            members = self._read_members(strict=True)
            key = str(user_id)
            current = _member_defaults(members.get(key))
            if current is None:
                return RESULT_MISSING
            if current["status"] != MEMBER_PENDING:
                return RESULT_NOT_PENDING
            current["status"] = MEMBER_APPROVED
            members[key] = current
            self._write_members(members)
            return RESULT_APPROVED

    async def reject_pending(self, user_id: int) -> PendingResult:
        """pending → record deleted, atomically. Non-pending records are kept."""
        async with self._lock:
            members = self._read_members(strict=True)
            key = str(user_id)
            current = _member_defaults(members.get(key))
            if current is None:
                return RESULT_MISSING
            if current["status"] != MEMBER_PENDING:
                return RESULT_NOT_PENDING
            del members[key]
            self._write_members(members)
            return RESULT_REJECTED

    async def remove_member(self, user_id: int) -> bool:
        """Removing a member: status="removed", roles cleared, record kept (history).

        The head-lead flag is dropped in the same critical section so a removed person
        can never remain the (stale) recipient of request cards.
        """
        async with self._lock:
            members = self._read_members(strict=True)
            key = str(user_id)
            current = members.get(key)
            if not isinstance(current, dict):
                return False
            current["status"] = MEMBER_REMOVED
            current["roles"] = []
            current.pop("is_head_lead", None)
            members[key] = current
            self._write_members(members)
            return True

    async def add_role(self, user_id: int, role: str) -> list[str] | None:
        """Adds the role if it is known and the member exists in the roster."""
        if role not in ROLES:
            return None
        async with self._lock:
            members = self._read_members(strict=True)
            key = str(user_id)
            current = members.get(key)
            if not isinstance(current, dict):
                return None
            roles = _roles_of(current)
            if role not in roles:
                roles.append(role)
            self._write_members(members)
            return list(roles)

    async def remove_role(self, user_id: int, role: str) -> list[str] | None:
        """Removes the role; returns None if there is no roster entry."""
        async with self._lock:
            members = self._read_members(strict=True)
            key = str(user_id)
            current = members.get(key)
            if not isinstance(current, dict):
                return None
            roles = _roles_of(current)
            if role in roles:
                roles.remove(role)
            self._write_members(members)
            return list(roles)

    async def list_members(
        self, status: MemberState | None = None, role: str | None = None
    ) -> list[tuple[int, dict[str, Any]]]:
        """[(user_id, member)] with filters by status and/or role; ids are numeric."""
        result: list[tuple[int, dict[str, Any]]] = []
        for key, value in self._read_members().items():
            member = _member_defaults(value)
            if member is None:
                continue
            try:
                user_id = int(key)
            except ValueError:
                logger.warning("Skipping roster entry with a non-numeric key: %r", key)
                continue
            if status is not None and member["status"] != status:
                continue
            if role is not None and role not in member["roles"]:
                continue
            result.append((user_id, member))
        return result

    # ---------- head lead ----------

    async def get_head_lead(self) -> int | None:
        """Head group lead ID or None. Tolerant read: bad data is treated as no lead.

        If several entries carry the `is_head_lead` flag, the first one wins and a
        warning is logged — the flag is meant to be unique.
        """
        head_lead_id: int | None = None
        for key, value in self._read_members().items():
            if not (isinstance(value, dict) and value.get("is_head_lead") is True):
                continue
            if head_lead_id is not None:
                logger.warning("Multiple is_head_lead flags in members.json; using the first")
                break
            try:
                head_lead_id = int(key)
            except ValueError:
                # Tolerant read: skip the broken entry — another valid flag may exist.
                logger.warning("Roster lead entry has a non-numeric key: %r", key)
        return head_lead_id

    async def set_head_lead(self, user_id: int | None) -> int | None:
        """Sets (or clears) the head group lead — the recipient of requests.

        The flag is cleared on every entry first, then placed on the requested
        member (if it exists): the invariant is exactly one lead or none at all.
        Returns the stored lead id, or None if it was cleared / had no roster entry.
        """
        async with self._lock:
            members = self._read_members(strict=True)
            for value in members.values():
                if isinstance(value, dict):
                    value.pop("is_head_lead", None)
            stored = False
            if user_id is not None:
                current = members.get(str(user_id))
                if isinstance(current, dict):
                    current["is_head_lead"] = True
                    stored = True
            self._write_members(members)
            return user_id if stored else None
