"""K2: version contract (ruff target)."""

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def test_ruff_targets_python_311():
    pyproject = (ROOT / "pyproject.toml").read_text(encoding="utf-8")

    assert 'target-version = "py311"' in pyproject
