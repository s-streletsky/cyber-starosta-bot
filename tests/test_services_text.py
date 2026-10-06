"""Tests for services/text.py: newline-aware message chunking."""

from services.text import split_message


def test_split_message_short_single_line():
    assert split_message("hello", 100) == ["hello"]


def test_split_message_empty():
    assert split_message("", 100) == [""]


def test_split_message_multiline_under_limit():
    text = "first\nsecond\nthird"

    chunks = split_message(text, 100)

    assert chunks == [text]
    assert "\n".join(chunks) == text


def test_split_message_exceeding_limit_splits_on_newlines():
    text = "\n".join("x" * 30 for _ in range(10))

    chunks = split_message(text, 100)

    assert len(chunks) > 1
    assert all(len(chunk) <= 100 for chunk in chunks)
    assert "\n".join(chunks) == text


def test_split_message_counts_the_newline_separator():
    text = "a" * 50 + "\n" + "b" * 50

    assert split_message(text, 100) == ["a" * 50, "b" * 50]
    assert split_message(text, 101) == [text]


def test_split_message_single_line_over_limit_stays_intact():
    line = "z" * 150

    assert split_message(line, 100) == [line]


def test_split_message_counts_astral_emoji_as_code_points():
    text = "😀" * 4 + "\n" + "a" * 5

    assert split_message(text, 10) == [text]
