"""Global pytest setup: project root in sys.path and a BOT_TOKEN stub."""

import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

# config.py fails without a token and without at least one admin (fail-fast).
os.environ.setdefault("BOT_TOKEN", "123456:TEST")
os.environ.setdefault("ADMIN_USER_IDS", "999999999")
