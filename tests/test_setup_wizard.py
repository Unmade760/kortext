"""
Tests for Kortext Guided Setup Wizard, Diagnostics, and Substrate Provisioning.
"""
from pathlib import Path
from unittest.mock import MagicMock, patch
import pytest

from kortext.setup import (
    get_kortext_home,
    is_port_open,
    is_unix_socket_open,
    provision_directories,
    run_diagnostics,
    SetupDiagnostics,
    start_substrates,
    stop_substrates,
)
from kortext.cli import main


def test_get_kortext_home():
    home = get_kortext_home()
    assert isinstance(home, Path)
    assert home.name in (".kortext", ".cerebrum") or "kortext" in str(home).lower()


def test_provision_directories(tmp_path):
    created = provision_directories(tmp_path)
    assert len(created) >= 15
    # Verify 8-category journal directories are created
    categories = [
        "decisions", "roadmaps", "implementations", "experiments",
        "benchmarks", "investigations", "research", "reports", "dreams"
    ]
    for cat in categories:
        cat_dir = tmp_path / "journal" / cat
        assert cat_dir.is_dir(), f"Missing journal taxonomy dir: {cat}"
    assert (tmp_path / "run").is_dir()
    assert (tmp_path / "logs").is_dir()
    assert (tmp_path / "data" / "falkordb").is_dir()


def test_run_diagnostics():
    diag = run_diagnostics()
    assert isinstance(diag, SetupDiagnostics)
    assert diag.os_name in ("Darwin", "Linux", "Windows")
    assert isinstance(diag.python_compatible, bool)
    assert isinstance(diag.installed_grammars, tuple)
    assert Path(diag.kortext_home).exists()


def test_is_port_open_closed():
    # An improbable local port should return False
    assert is_port_open("127.0.0.1", 59999, timeout=0.1) is False


def test_is_unix_socket_open_nonexistent(tmp_path):
    fake_sock = tmp_path / "nonexistent.sock"
    assert is_unix_socket_open(fake_sock) is False


def test_cli_setup_parser(capsys):
    with patch("sys.argv", ["kortext", "setup", "--yes"]):
        main()
    captured = capsys.readouterr()
    assert "GUIDED SETUP WIZARD" in captured.out
    assert "SETUP COMPLETE" in captured.out


def test_cli_status_parser(capsys):
    with patch("sys.argv", ["kortext", "status"]):
        main()
    captured = capsys.readouterr()
    assert "Kortext Substrate Health" in captured.out
    assert "FalkorDB" in captured.out
