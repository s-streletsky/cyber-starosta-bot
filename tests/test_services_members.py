"""Tests for services/members.py: full-name validation, labels, roles."""

import pytest

from services.members import (
    ROLE_GROUP_LEAD,
    member_label,
    role_name,
    validate_full_name,
)


def test_valid_names():
    assert validate_full_name("Петренко Іван") == "Петренко Іван"
    assert validate_full_name("Д'яков Олександр") == "Д'яков Олександр"
    assert validate_full_name("Д’яков Олександр") == "Д’яков Олександр"
    assert validate_full_name("Анна-Марія Петренко") == "Анна-Марія Петренко"
    assert validate_full_name("  Іван   Петров  ") == "Іван Петров"


def test_invalid_word_count():
    for bad in ("", "Іван", "Іван Іванів Іванів", "   "):
        with pytest.raises(ValueError):
            validate_full_name(bad)


def test_invalid_characters():
    for bad in ("Іван1 Петров", "Ів- --", "Іван Петров!", "1 2"):
        with pytest.raises(ValueError):
            validate_full_name(bad)


def test_invalid_length():
    with pytest.raises(ValueError):
        validate_full_name("а" * 61 + " б")
    with pytest.raises(ValueError):
        validate_full_name("А б")


def test_member_label():
    assert member_label({"display_name": "Петренко Іван", "username": "ivan"}) == (
        "Петренко Іван (@ivan)"
    )
    assert member_label({"display_name": "Петренко Іван", "username": None}) == "Петренко Іван"


def test_role_name():
    assert role_name(ROLE_GROUP_LEAD) == "староста"
    assert role_name("unknown") == "unknown"
