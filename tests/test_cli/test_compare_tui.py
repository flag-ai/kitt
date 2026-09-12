"""Tests for the comparison TUI module."""

import pytest

from kitt.cli.compare_tui import TEXTUAL_AVAILABLE, check_textual_available


@pytest.mark.skipif(not TEXTUAL_AVAILABLE, reason="textual not installed")
def test_textual_available():
    """Textual should be available when installed."""
    assert check_textual_available() is True


def test_textual_not_available_returns_bool():
    """check_textual_available always returns a bool."""
    result = check_textual_available()
    assert isinstance(result, bool)
