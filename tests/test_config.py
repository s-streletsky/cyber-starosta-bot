"""Tests for config.py: fail-fast on a missing token and a broken timezone."""

import os
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def _run_import_config(extra_env: dict[str, str]) -> subprocess.CompletedProcess[str]:
    # override=False in load_dotenv: os.environ values win over .env → the test is deterministic.
    env = {**os.environ, "BOT_TOKEN": "", **extra_env}
    return subprocess.run(
        [sys.executable, "-c", "import config"],
        cwd=ROOT,
        env=env,
        capture_output=True,
        text=True,
    )


def test_missing_token_fails_fast():
    result = _run_import_config({})

    assert result.returncode != 0
    assert "BOT_TOKEN is not set" in result.stderr


def test_invalid_timezone_fails_fast():
    result = _run_import_config({"BOT_TOKEN": "123456:TEST", "TIMEZONE": "Not/AZone"})

    assert result.returncode != 0
    assert "is not a valid time zone" in result.stderr


def test_empty_admin_ids_fails_fast():
    result = _run_import_config(
        {"BOT_TOKEN": "123456:TEST", "TIMEZONE": "Europe/Kyiv", "ADMIN_USER_IDS": ""}
    )

    assert result.returncode != 0
    assert "ADMIN_USER_IDS is not set" in result.stderr
