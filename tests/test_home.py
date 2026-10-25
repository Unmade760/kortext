"""
Unit tests for storage home resolution in kortext._home.
"""

import os
from pathlib import Path
from unittest.mock import patch
import pytest

from kortext._home import get_kortext_home, KORTEXT_HOME
import kortext


def test_kortext_home_constant_is_path():
    assert isinstance(KORTEXT_HOME, Path)


def test_kortext_init_exports():
    assert hasattr(kortext, "get_kortext_home")
    assert hasattr(kortext, "KORTEXT_HOME")
    assert kortext.get_kortext_home is get_kortext_home
    assert kortext.KORTEXT_HOME == KORTEXT_HOME


def test_get_kortext_home_from_env(monkeypatch, tmp_path):
    custom_dir = tmp_path / "custom_kortext"
    monkeypatch.setenv("KORTEXT_HOME", str(custom_dir))
    assert get_kortext_home() == custom_dir


def test_get_kortext_home_fallback_to_kortext_dir(monkeypatch, tmp_path):
    monkeypatch.delenv("KORTEXT_HOME", raising=False)
    fake_home = tmp_path / "user_home"
    k_dir = fake_home / ".kortext"
    k_dir.mkdir(parents=True)

    with patch.object(Path, "home", return_value=fake_home):
        assert get_kortext_home() == k_dir


def test_get_kortext_home_default_when_neither_exists(monkeypatch, tmp_path):
    monkeypatch.delenv("KORTEXT_HOME", raising=False)
    fake_home = tmp_path / "user_home"
    fake_home.mkdir(parents=True)

    with patch.object(Path, "home", return_value=fake_home):
        assert get_kortext_home() == fake_home / ".kortext"
