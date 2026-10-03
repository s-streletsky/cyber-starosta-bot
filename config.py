"""Bot configuration: environment variables and fail-fast validation."""

import logging
import os
import sys
import tempfile
from pathlib import Path
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from dotenv import load_dotenv

load_dotenv()

logger = logging.getLogger(__name__)

# storage.py relies on datetime.UTC (Python 3.11+); guard before anything imports it.
if sys.version_info < (3, 11):
    logger.critical("Python 3.11+ required")
    raise SystemExit("Python 3.11+ required")


def _parse_user_ids(name: str) -> list[int]:
    """CSV list of IDs: garbage is ignored with a warning instead of failing the bot."""
    raw = os.getenv(name, "")
    user_ids: list[int] = []
    for part in raw.split(","):
        part = part.strip()
        if not part:
            continue
        try:
            user_ids.append(int(part))
        except ValueError:
            logger.warning("%s: %r is not a numeric ID — skipped", name, part)
    return user_ids


BOT_TOKEN = os.getenv("BOT_TOKEN", "").strip()
if not BOT_TOKEN:
    logger.critical("BOT_TOKEN is not set. Create .env file with BOT_TOKEN=your_token")
    raise SystemExit("BOT_TOKEN is not set. Create .env file with BOT_TOKEN=your_token")

# Admins (bootstrap): several IDs can be set in env separated by commas. The role
# is NOT stored in the roster — it is resolved from env on the fly. An admin can use
# /pending, /promote, /demote, /remove, /sethead; it cannot be /demote//removed.
ADMIN_USER_IDS = _parse_user_ids("ADMIN_USER_IDS")
if not ADMIN_USER_IDS:
    logger.critical("ADMIN_USER_IDS is not set. Configure at least one admin ID.")
    raise SystemExit("ADMIN_USER_IDS is not set. Configure at least one admin ID.")

DATA_DIR = Path(os.getenv("DATA_DIR", "./data"))
try:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile(dir=DATA_DIR, prefix=".write_test-", delete=True):
        pass
except OSError as exc:
    logger.critical("DATA_DIR=%s is not writable: %s", DATA_DIR, exc)
    raise SystemExit(f"DATA_DIR={DATA_DIR} is not writable: {exc}") from exc

TIMEZONE = os.getenv("TIMEZONE", "Europe/Kyiv")
try:
    TZ = ZoneInfo(TIMEZONE)
except (ZoneInfoNotFoundError, ValueError, OSError) as exc:
    logger.critical("TIMEZONE=%r is not a valid time zone", TIMEZONE)
    raise SystemExit(f"TIMEZONE={TIMEZONE!r} is not a valid time zone") from exc

BOT_BRAND_NAME = os.getenv("BOT_BRAND_NAME", "CyberStarostaBot")
