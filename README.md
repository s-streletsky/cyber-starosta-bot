# Cyber Starosta Bot

Telegram bot for a small student group (~30 people). Students mark the days they
will be absent; the group lead reviews join requests and manages roles. All data
lives in plain files — no database.

- Stack: Python 3.11+ (developed on 3.13), [aiogram](https://docs.aiogram.dev/) 3.15,
  python-dotenv.
- Persistence: `<DATA_DIR>/absences.jsonl` (append-only absence journal) and
  `<DATA_DIR>/members.json` (group roster). No DB.
- Language: all user-facing texts are Ukrainian.

## 1. Features

- **Join by request.** A student sends `/start` and their full name; the request
  goes to the head group lead (or to env admins while no lead is assigned).
  Approval is a button tap on the request card.
- **Role-based access.** `group_lead`, `supervisor` and bootstrap admins have
  different rights; the menu is built from those rights, not hard-coded.
- **Marking absences.** A student picks one or more of the next three days, a
  reason (or free text), and confirms. Re-marking the same date with a different
  reason replaces the old record; re-sending an identical record is a no-op.
- **Admin management.** `/promote`, `/demote`, `/remove`, `/sethead` and
  `/pending` work through inline buttons — no IDs need to be typed.
- **Crash-safe storage.** Absences are appended and fsync'd; the roster is written
  atomically (temp file + `os.replace`). A corrupt roster is snapshotted and never
  silently overwritten.

## 2. Requirements

- Python **3.11+** (the code uses `datetime.UTC` and `zoneinfo`).
- A bot token from [@BotFather](https://t.me/BotFather).
- At least one numeric Telegram admin ID — the bot **refuses to start without
  `ADMIN_USER_IDS`** (get yours via [@userinfobot](https://t.me/userinfobot)).
- On Windows, `tzdata` for `zoneinfo` (declared in the `dev` dependency group in
  `pyproject.toml`).

## 3. Local run

```bash
git clone <your-repo-url> cyber-starosta-bot
cd cyber-starosta-bot
python -m venv venv
venv/bin/pip install -r requirements.txt     # Windows: venv\Scripts\pip install -r requirements.txt
cp .env.example .env
# open .env and set BOT_TOKEN and ADMIN_USER_IDS
python -m bot
```

Both `python -m bot` and `python bot.py` work; the systemd unit uses `bot.py`.

`.env` variables:

| Variable | Purpose |
| --- | --- |
| `BOT_TOKEN` | token from @BotFather, required (bot refuses to start without it) |
| `ADMIN_USER_IDS` | comma-separated bootstrap admin IDs, required |
| `DATA_DIR` | data directory, default `./data` |
| `TIMEZONE` | time zone, default `Europe/Kyiv` (validated on startup) |
| `BOT_BRAND_NAME` | bot name shown in messages, default `CyberStarostaBot` |

Local runs use `DATA_DIR=./data`; the server install uses
`/var/lib/cyber-starosta-bot` (section 4).

For development, install the dev dependencies and run the checks:

```bash
venv/bin/pip install -r requirements.txt --group dev
ruff check .
pytest -q
```

`--group` requires pip >= 25.1: upgrade with `python -m pip install --upgrade pip`.
The Ubuntu server install (section 4) does not use `--group` — it installs the
runtime dependencies only.

### Local testing (Windows, PowerShell)

Test with a separate **test** bot (create one via @BotFather) so the production
bot is untouched:

1. Copy `.env.example` to `.env` and set `BOT_TOKEN` and `ADMIN_USER_IDS` (the
   bot refuses to start without an admin ID).
2. Install dev dependencies and run: `.\venv\Scripts\pip install -r requirements.txt --group dev`
   then `python -m bot`. You are now an admin (`/promote`, `/demote`, `/remove`,
    `/sethead`, `/pending`).
3. Role flow needs a **second Telegram account**: it sends `/start` and a name
   (e.g. «Петренко Іван»); the request card goes to the head lead (or admins if
   no lead is assigned). Approve via `✅ Прийняти` — the student gets the menu
   and can mark absences.
4. Reset test data while the bot is **stopped**: delete `data\absences.jsonl`,
   `data\members.json` and `data\members.corrupt-*.json`. On restart the bot
   starts with an empty roster.

On Windows `tzdata` is required for `zoneinfo` (declared in the `dev` dependency
group in `pyproject.toml`). Long polling needs direct access to `api.telegram.org`;
a proxy or network block causes a connection timeout.

## 4. Server deployment

Manual install for Ubuntu/Debian with `sudo`. Use a dedicated system user and a
state directory outside the read-only code tree.

> **Canonical data dir: `/var/lib/cyber-starosta-bot`.** Keep it —
> `deploy/backup.sh` hardcodes this path, so a different `DATA_DIR` makes the daily
> backup fail (the oneshot exits non-zero when it copies nothing).

### 4.1 Install

1. System packages:

   ```bash
   sudo apt update
   sudo apt install -y python3 python3-pip python3-venv tzdata git nano
   python3 --version   # must be 3.11 or newer
   ```

2. Dedicated system user (no login; idempotent):

   ```bash
   id -u cyber-starosta >/dev/null 2>&1 || \
     sudo useradd -r -s /usr/sbin/nologin -M cyber-starosta
   ```

3. Clone the code:

   ```bash
   sudo mkdir -p /opt
   sudo git clone <your-repo-url> /opt/cyber-starosta-bot
   ```

4. Virtualenv and dependencies:

   ```bash
   cd /opt/cyber-starosta-bot
   sudo python3 -m venv venv
   sudo venv/bin/pip install --upgrade pip
   sudo venv/bin/pip install -r requirements.txt
   ```

5. Ownership and permissions (code root-owned, read-only for the bot):

   ```bash
   sudo chown -R root:cyber-starosta /opt/cyber-starosta-bot
   sudo chmod -R g+rX,o-rwx /opt/cyber-starosta-bot
   sudo chown root:root /opt/cyber-starosta-bot/deploy/backup.sh
   sudo chmod 0755 /opt/cyber-starosta-bot/deploy/backup.sh
   ```

6. Data and backup directories (the data dir must exist and be writable before
   the first start):

   ```bash
   sudo install -d -m 0750 -o cyber-starosta -g cyber-starosta /var/lib/cyber-starosta-bot
   sudo install -d -m 0700 -o root -g root /var/backups/cyber-starosta-bot
   ```

7. Environment file with an authoritative server `DATA_DIR`:

   ```bash
   sudo install -d -m 0755 -o root -g root /etc/cyber-starosta-bot
   sudo tee /etc/cyber-starosta-bot/env >/dev/null <<'EOF'
   BOT_TOKEN=REPLACE_WITH_TOKEN_FROM_BOTFATHER
   ADMIN_USER_IDS=REPLACE_WITH_YOUR_NUMERIC_ID
   DATA_DIR=/var/lib/cyber-starosta-bot
   TIMEZONE=Europe/Kyiv
   BOT_BRAND_NAME=Cyber Starosta
   EOF
   sudo chmod 600 /etc/cyber-starosta-bot/env
   sudo nano /etc/cyber-starosta-bot/env   # fill BOT_TOKEN and ADMIN_USER_IDS
   ```

   > Do **not** copy `.env.example` to the server: it ships `DATA_DIR=./data`,
   > which is only correct for local runs. The service runs with
   > `WorkingDirectory=/opt/cyber-starosta-bot`, which the bot user cannot write
   > to, so `./data` leads to a restart loop and empty backups.

8. Bot service:

   ```bash
   sudo cp /opt/cyber-starosta-bot/deploy/cyber-starosta-bot.service /etc/systemd/system/
   sudo systemctl daemon-reload
   sudo systemctl enable cyber-starosta-bot
   sudo systemctl start cyber-starosta-bot
   ```

9. Backup service and timer (details — section 7):

   ```bash
   sudo cp /opt/cyber-starosta-bot/deploy/cyber-starosta-backup.service /etc/systemd/system/
   sudo cp /opt/cyber-starosta-bot/deploy/cyber-starosta-backup.timer /etc/systemd/system/
   sudo systemctl daemon-reload
   sudo systemctl enable --now cyber-starosta-backup.timer
   ```

10. Verify:

    ```bash
    sudo systemctl status cyber-starosta-bot --no-pager
    sudo journalctl -u cyber-starosta-bot -n 30 --no-pager    # no PermissionError; the unit gives up after repeated failures
    sudo -u cyber-starosta test -w /var/lib/cyber-starosta-bot && echo "data dir writable"
    ls -ld /var/lib/cyber-starosta-bot /etc/cyber-starosta-bot/env
    sudo ls -la /var/lib/cyber-starosta-bot/                  # after a /start: members.json etc.
    sudo -u nobody cat /var/lib/cyber-starosta-bot/members.json   # Permission denied
    sudo systemctl start cyber-starosta-backup.service
    sudo ls -la /var/backups/cyber-starosta-bot/$(date +%F)/      # files present, mode 600
    ```

The service (`deploy/cyber-starosta-bot.service`) runs `venv/bin/python bot.py`
as `cyber-starosta`, reads `/etc/cyber-starosta-bot/env`, and restarts on
failure. Restarts are bounded (`StartLimitIntervalSec=300`, `StartLimitBurst=5`),
so after repeated fail-fast config errors the unit gives up instead of spinning
forever. `StateDirectory=cyber-starosta-bot` makes systemd create
`/var/lib/cyber-starosta-bot` with mode `0750` on start.

## 5. Roles, menu and commands

Roles are resolved from the roster. Bootstrap admins come from `ADMIN_USER_IDS`;
their admin rights are resolved from the environment on every check, never from
roster roles. An admin still gets a normal approved roster entry on `/start`
(for name/username), but it carries no admin role and cannot be demoted or
removed.

| Role | Rights |
| --- | --- |
| Student (approved) | Mark own absences; `🗂 Мене не буде` |
| Group lead (`group_lead`) | Student rights + review requests (`/pending`); can be the head lead |
| Supervisor (`supervisor`) | Selections only (`📊 Вибірки`); **cannot** mark absences |
| Env admin | Everything, including role management; cannot be demoted or removed |

`📊 Вибірки` is currently a placeholder — it replies that selections will arrive
in a future update.

### First run and admin tasks

1. Put your numeric ID into `ADMIN_USER_IDS` in the env file (several IDs —
   comma-separated) and restart the bot.
2. A student sends `/start` and their **surname and name** (e.g. «Петренко Іван»).
   The request card goes to the head lead, or to all env admins if no lead is
   assigned.
3. The recipient taps `✅ Accept` or `❌ Reject`. An approved student gets the menu
   and can mark absences.
4. Commands:
   - `/pending` — list of pending requests (group leads and admins).
   - `/sethead` — choose the head lead: the recipient of new request cards.
   - `/promote` — grant a role (👑 Group Lead or 🎓 Supervisor) via buttons.
   - `/demote` — remove a role from a person.
   - `/remove` — close access (past records are kept; the person can re-apply).
   - `/cancel` — cancel the free-text reason step of the absence flow.

External edits to `members.json` (e.g. fixing a `display_name`) are picked up on
the next read: the bot only updates `username` on repeated `/start`, never
`display_name`, status or roles.

## 6. Data format (internal)

Files in `<DATA_DIR>`:

- `absences.jsonl` — append-only journal, UTF-8, LF, one JSON object per line:

  ```json
  {"user_id": 42, "date": "2026-09-29", "reason": "illness", "reason_text": null, "created_at": "2026-09-28T19:14:51Z"}
  ```

  Records are keyed by `(user_id, date)` and **the last line wins**. Replacing a
  record appends a new line; old lines are never deleted.

- `members.json` — the roster, keyed by numeric user id:

  ```json
  {
    "42": {
      "display_name": "Петренко Іван",
      "username": "ivan",
      "status": "approved",
      "roles": []
    }
  }
  ```

  `status` is `approved`, `pending` or `removed`. `roles` may contain
  `group_lead` and/or `supervisor`. An optional `"is_head_lead": true` marks the head
  lead; there is exactly one head lead or none — `/sethead` sets the flag on one
  member and clears it from everyone else.

Reason codes (defined in `services/absence.py`, the source of truth):

| Code | Meaning |
| --- | --- |
| `illness` | 💊 Illness |
| `academic` | 🎓 Other class / retake |
| `event` | 🏆 Competition / trip |
| `family` | 👨‍👩‍👧 Family matters |
| `transport` | 🚇 Transport / traffic |
| `excused` | 📋 Excused absence |
| `other` | ✍️ Other (free text in `reason_text`) |

### Corrupted roster (`members.corrupt-*`)

If `members.json` is invalid JSON, the bot does not silently overwrite it: on the
first write attempt it saves a snapshot next to it as
`members.corrupt-<timestamp>.json` and refuses to write (the write is lost, the
log shows `critical`). Only the first snapshot of a given file is kept. On the
first `StorageCorruptError`, `bot.py` also sends a Telegram alert to every env
admin (`texts.ADMIN_STORAGE_ALERT`) once per process, so someone is notified
without reading the journal. To recover: stop the bot, inspect the snapshot and
the current `members.json`, fix/restore the JSON manually, then start the bot
again.

## 7. Backup and restore

A daily systemd timer (`deploy/cyber-starosta-backup.timer`, running the oneshot
`cyber-starosta-backup.service` as root) executes `deploy/backup.sh`, which copies
`absences.jsonl` and `members.json` to
`/var/backups/cyber-starosta-bot/<YYYY-MM-DD>/` (directory `700`, files `600`)
and prunes directories older than 30 days.

Restore:

```bash
sudo systemctl stop cyber-starosta-bot
BACKUP=/var/backups/cyber-starosta-bot/$(date +%F)   # or a specific date
sudo install -d -m 0750 -o cyber-starosta -g cyber-starosta /var/lib/cyber-starosta-bot
sudo install -m 640 -o cyber-starosta -g cyber-starosta \
  "$BACKUP/absences.jsonl" /var/lib/cyber-starosta-bot/absences.jsonl
sudo install -m 640 -o cyber-starosta -g cyber-starosta \
  "$BACKUP/members.json" /var/lib/cyber-starosta-bot/members.json
sudo systemctl start cyber-starosta-bot
sudo journalctl -u cyber-starosta-bot -n 30 --no-pager   # verify
```

## 8. Semi-annual journal cleanup

`absences.jsonl` grows forever, so archive and truncate it occasionally:

```bash
sudo systemctl stop cyber-starosta-bot
sudo install -d -m 0750 -o cyber-starosta -g cyber-starosta \
  /var/lib/cyber-starosta-bot/archive
sudo gzip -c /var/lib/cyber-starosta-bot/absences.jsonl \
  > /var/lib/cyber-starosta-bot/archive/absences-$(date +%F).jsonl.gz
sudo chmod 640 /var/lib/cyber-starosta-bot/archive/absences-$(date +%F).jsonl.gz
: > /var/lib/cyber-starosta-bot/absences.jsonl
sudo chown cyber-starosta:cyber-starosta /var/lib/cyber-starosta-bot/absences.jsonl
sudo systemctl start cyber-starosta-bot
```

**Do not touch the roster `members.json`.** Stop the bot before cleanup so its
in-memory index is not stale: on restart the journal is empty and so is the index.

## 9. Data permissions

The roster (names, IDs) and absence journal are personal data:

- the bot runs under a dedicated system user `cyber-starosta` (no login), so
  compromising the bot does not grant access to the rest of the server;
- the data directory `/var/lib/cyber-starosta-bot` is `750` and its files are
  `640` — only the bot user (and root) can read them;
- the project code is owned by root; the bot cannot modify its own files;
- backups live in `/var/backups/cyber-starosta-bot` with `700`/`600`;
- manual edits to `members.json` are done via `sudo nano` (root can always read).

Verify: `sudo -u nobody cat /var/lib/cyber-starosta-bot/members.json` should print
Permission denied.

## 10. Project layout

```
bot.py            Entry point: Bot/Dispatcher, middleware, error handler, polling
config.py         Env loading and fail-fast validation
storage.py        File persistence (append-only journal + atomic roster), one lock
services/         Pure business logic (no aiogram): members, absence
handlers/         aiogram routers: start, pending, admin, absence, reply_menu,
                  notify, middleware, log_helpers
keyboards/        Keyboards built from service predicates
callbacks.py      CallbackData factories and action constants
texts.py          All user-facing Ukrainian strings
deploy/           systemd units and the backup script
tests/            pytest suite (asyncio_mode = auto)
```

Architecture rules, code conventions and the verification checklist are in
[`AGENTS.md`](AGENTS.md).

## 11. Verification

```bash
ruff check .
pytest -q
mypy
compileall -q -x venv .
```
