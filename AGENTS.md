# AGENTS.md — cyber-starosta-bot project contract

## Stack and run
- Python >= 3.11 (code uses `datetime.UTC`).
- Dependencies: `aiogram==3.31.0`, `python-dotenv`.
- Dev: `pytest==9.1.1`, `pytest-asyncio==1.4.0`, `ruff==0.16.9`, `mypy==1.11.2`, `tzdata==2026.4` (Windows).
- Reproducible installs: `requirements.txt` pins the full runtime transitive
  closure; dev tools live in `pyproject.toml` under `[dependency-groups] dev` and
  are installed with `pip install -r requirements.txt --group dev`.
- venv: `.\venv\Scripts\python.exe` (Windows) / `./venv/bin/python` (Linux).
- Run: `python -m bot` from root. Requires `.env` with `BOT_TOKEN` and `ADMIN_USER_IDS`.

## Architecture (strict layering)
- `config.py` — env + fail-fast validation.
- `storage.py` — persistence: `<DATA_DIR>/absences.jsonl` (append-only journal) +
  `<DATA_DIR>/members.json` (atomic roster). No DB. All mutations under `asyncio.Lock`.
  Absences support logical deletion: `delete_absences_batch` appends a tombstone
  (`ABSENCE_DELETED`, `is_deleted`); a deleted key reads as absent (`get_record` →
  `None`) and is excluded from `list_absences_for_date`, so reports skip it.
  Re-marking a deleted key appends a fresh active record (`ABSENCE_CREATED`).
  Per-date mutations are capped at `ABSENCE_ATTEMPT_LIMIT` (10) per
  `(user_id, date)`, lifetime; the counter is journal-derived (rebuilt on load, no
  new file), identical re-marks consume nothing, delete consumes one, and a blocked
  mutation returns `ABSENCE_LIMIT`. Env admins bypass the cap via the
  `enforce_limit` flag the handlers compute; `storage.py` never imports `config`.
- Storage invariant: all mutations run under one `asyncio.Lock` with synchronous
  (no `await`) file I/O inside the critical section; reads (`get_record`,
  `list_absences_for_date`) are lock-free and rely on that invariant, returning
  copies. Do not introduce `await` points into `_write_members`/
  `_append_line` or the read paths.
- Head lead: an optional boolean `is_head_lead` on a roster entry marks the single
  main lead (recipient of request cards); exactly one or none. Read/set via
  `get_head_lead`/`set_head_lead`, chosen with `/sethead`; the flag is dropped on
  resubmit and remove.
- Corruption: reading a corrupt `members.json` tolerates it (empty + log); a write
  takes one best-effort snapshot (`members.corrupt-*.json`) and raises
  `StorageCorruptError` instead of overwriting. `bot.py` alerts all env admins once
  per process on the first `StorageCorruptError`.
- `services/` — pure business logic, no aiogram: `members.py` (validation, rights),
  `absence.py` (days, reasons, summary), `help.py` (role-filtered `/help` catalog),
  `text.py` (newline-aware message chunking).
- `handlers/` — aiogram routers: `start`, `help`, `cancel`, `pending`, `admin`,
  `report`, `absence`, `reply_menu`, `notify`, `middleware`, `log_helpers`
  (orchestration only, no business logic).
- `keyboards/` — keyboards built from `services` predicates and domain tables
  (`services.members`, `services.absence.REASONS`).
- `callbacks.py` — CallbackData factories (no raw strings in handlers).
- `bot.py` — composition root (`build_dispatcher()` wires the ACL middleware + routers
  in one shared path for production and integration tests; DI storage via `dp.workflow_data`).
- `texts.py` — all user-facing strings (Ukrainian), except domain label tables
  that live in `services` (`REASONS`, `_REASON_LABELS`, `_WEEKDAYS`, `_DAY_PREFIXES`,
  `_ROLE_NAMES` — tied to business logic and ordering).

Dependencies: handlers → services → storage. No reverse deps.
  Handler-to-handler imports are allowed for shared utilities, e.g. `start→pending`,
  `start→log_helpers`, `absence→reply_menu`, `middleware→start`,
  `middleware→log_helpers`, `pending→notify`, `pending→log_helpers`,
  `notify→log_helpers`, `admin→notify`, `cancel→reply_menu` — document new ones here.
  Shared utilities: `notify`, `reply_menu`, `log_helpers` (the latter imported by
  `bot`, `start`, `pending`, `middleware` and `notify`).
  `handlers/report.py` uses `services.members`, `services.absence`,
  `services.text`, `keyboards.report` and `storage` only — it adds no
  handler-to-handler edge.
  `services/help.py` uses `texts` and `services.members` (new intra-service edge
  `help → members`); `handlers/help.py` uses `services.help`, `services.members`
  and `storage` (no handler-to-handler edge). `handlers/middleware.py` imports
  `services.help.OPEN_COMMANDS` (new edge `middleware → services.help`): the
  open-to-everyone message set is derived from the catalog's `AUDIENCE_ALL`
  entries instead of hardcoding `/start` and `/help`.
  `handlers/cancel.py` is registered first (before `/help`) so the global
  `/cancel` interrupts any FSM flow (onboarding + absence marking/deletion) and
  clears it; `cancel` is now an `AUDIENCE_ALL` entry, so `/cancel` is in
  `OPEN_COMMANDS` (open to everyone) and appears in the Telegram command menu.
  `services/help.py` `AUDIENCE_MANAGER` uses the approval-aware
  `services.members.is_active_group_lead`, so pending/removed group leads do not
  see `/pending` in `/help`; `handlers/pending.py`'s `_is_manager` keeps
  `services.members.can_process_requests` as the runtime guard after ACL admission.
`services`/`handlers` use `storage` constants (`MEMBER_APPROVED`, `ROLE_*`, `ABSENCE_*`)
  and pure helpers (e.g. `is_identical_absence` used in `services/absence.py`;
  `is_deleted` used only inside `storage.py`), `handlers/pending.py` also
  uses the `RESULT_*` verdict constants; `services` uses `texts` for localized string
  templates (e.g. `CONFIRM_*` in `services/absence.py`); `config.ADMIN_USER_IDS` is
  imported lazily inside `is_admin()`.
The reply menu gets a `MENU_DELETE` button (same `can_mark_absence` right) that starts
  the logical-deletion flow (states `AbsenceForm.delete_day` / `delete_confirm`,
  `DeleteCb` with actions `confirm`/`back`, `keyboards.absence.delete_confirm_keyboard`).
  This adds no handler-to-handler edge: `handlers/absence.py` keeps its existing
  `absence→reply_menu` import only.
The broadcast notifications feature adds `services/broadcast.py`, `keyboards/broadcast.py`
  and `handlers/broadcast.py`. New handler-to-handler edges: `broadcast→notify`
  (`notify_many`) and `broadcast→reply_menu`; new intra-service edge `broadcast→members`
  (`member_label`, sorted recipients). `handlers/broadcast.py` is registered immediately
  before `absence` (which owns the global callback catch-all), so the router order is now
  `cancel, help, start, pending, admin, report, broadcast, absence`. New predicate
  `services.members.can_send_notifications(member, is_admin)` delegates to
  `can_view_reports` and gates the reply-menu `MENU_BROADCAST` button
  (`keyboards.menu.role_keyboard`, order `[absence, delete]`, `[broadcast, reports]`).
  New callbacks `RecipientCb` (`br`), `BroadcastCtl` (`bc`) and `MessageCb` (`bm`); the
  send step reuses `ConfirmCb(action="send")`. `handlers/notify.py` gains `notify_many`,
  which returns `(delivered, failed)` and swallows per-recipient failures like
  `notify_safe`. The feature is a reply-menu button only — no slash command was added, so
  `services/help.py` `HELP_COMMANDS` and its drift test are untouched. The `message`
  step also has a plain-text hint handler (`BROADCAST_MSG_HINT`, mirroring
  `recipients_text_hint`) — handler-local, no new edge. Role predicates
  (`can_view_reports`/`can_send_notifications`) assume an already-admitted member:
  `AccessControlMiddleware` is the approval gate, and approval-awareness lives only in
  predicates that build pre-admission selectable lists (`is_active_group_lead`).

## Code conventions
- User texts (`texts.py`) — Ukrainian; logs, comments, docstrings — English.
- Logs: `id (@username)` format via `handlers/log_helpers.user_tag`.
  Never log full names, reason text, or message content.
- CallbackData — only factories in `callbacks.py`; no strings in handlers.
- Callback actions — constants in `callbacks.py`; raw action strings in
  handlers/keyboards forbidden.
- Access rights — only `services.members` predicates; role hardcoding forbidden.
- Statuses/results — constants in `storage.py`; inline literals forbidden.
- Storage — files only; no DB (sufficient for ~30 students).

## Testing
- pytest `asyncio_mode = "auto"`.
- Handler tests: fakes `_FakeMessage`/`_FakeCallback`/`_FakeState` +
  `SimpleNamespace` pattern — see `tests/test_handlers_absence.py`.
- Admin in tests: user_id `999999999` (`conftest.py` → `ADMIN_USER_IDS`).
- Tests for essential behavior only; no bloat.

## Verification (run after changes)
- `ruff check .`
- `pytest -q`
- `mypy`
- `compileall -q -x venv .`

## Linting / types
- ruff: `line-length = 100`, `target-version = py311`, `select = [E, F, I, W]`.
- mypy: core (`storage`, `services`, `keyboards`, `bot`, `config`, `callbacks`,
  `texts`) fully checked; `handlers.*` under override (aiogram union specifics).

## Git
- Commits only on explicit user request. Do not commit unprompted.
- Message format — Conventional Commits: `<type>: <short imperative description>`.
  Types: `feat`, `fix`, `chore`, `docs`, `refactor`, `test`, `build`, `ci`.
- English, imperative mood, no trailing period, subject ≤ 72 chars; one logical
  change per commit. Add a body only when the "why" is not obvious from the diff.
- Examples: `chore: add .gitignore`, `fix: keep reports button for head lead`,
  `refactor: rename top lead to head lead`.
