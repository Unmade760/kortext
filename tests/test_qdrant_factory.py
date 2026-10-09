"""
Unit tests for centralized Qdrant client factory and lifecycle management in kortext._qdrant.
"""

import logging
from pathlib import Path
from unittest.mock import MagicMock, patch
import pytest

from kortext._qdrant import (
    get_qdrant_client,
    get_sync_qdrant_client,
    get_async_qdrant_client,
    is_qdrant_online,
)
import kortext


def test_reexport_in_kortext_init():
    assert hasattr(kortext, "get_qdrant_client")
    assert kortext.get_qdrant_client is get_qdrant_client
    assert hasattr(kortext, "get_sync_qdrant_client")
    assert kortext.get_sync_qdrant_client is get_sync_qdrant_client
    assert hasattr(kortext, "get_async_qdrant_client")
    assert kortext.get_async_qdrant_client is get_async_qdrant_client


def test_get_qdrant_client_with_explicit_url():
    with patch("kortext._qdrant.QdrantClient") as mock_client:
        client = get_qdrant_client(url="http://remote-qdrant:6333", timeout=7.5)
        mock_client.assert_called_once_with(url="http://remote-qdrant:6333", timeout=7.5)
        assert client == mock_client.return_value


def test_get_qdrant_client_with_storage_path(tmp_path, caplog):
    caplog.set_level(logging.INFO)
    isolated_path = tmp_path / "isolated_store"

    with patch("kortext._qdrant.QdrantClient") as mock_client:
        client = get_qdrant_client(storage_path=isolated_path)
        assert isolated_path.exists()
        mock_client.assert_called_once_with(path=str(isolated_path))
        assert client == mock_client.return_value

    assert any(
        "Initializing isolated Embedded Qdrant at" in record.message
        for record in caplog.records
    )


def test_get_qdrant_client_default_uses_get_qdrant_url(monkeypatch):
    monkeypatch.setenv("KORTEXT_QDRANT_URL", "http://env-qdrant:6333")

    with patch("kortext._qdrant.QdrantClient") as mock_client:
        client = get_qdrant_client(timeout=3.0)
        mock_client.assert_called_once_with(url="http://env-qdrant:6333", timeout=3.0)
        assert client == mock_client.return_value


def test_get_qdrant_client_storage_path_none_defaults_to_url(monkeypatch):
    monkeypatch.setenv("KORTEXT_QDRANT_URL", "http://default-qdrant:6333")

    with patch("kortext._qdrant.QdrantClient") as mock_client:
        client = get_qdrant_client(storage_path=None, timeout=5.0)
        mock_client.assert_called_once_with(url="http://default-qdrant:6333", timeout=5.0)
        assert client == mock_client.return_value


def test_get_async_qdrant_client_with_url():
    with patch("kortext._qdrant.AsyncQdrantClient") as mock_async_client:
        client = get_async_qdrant_client(url="http://custom-async:6333", timeout=2.5)
        mock_async_client.assert_called_once_with(url="http://custom-async:6333", timeout=2.5)
        assert client == mock_async_client.return_value


def test_get_async_qdrant_client_default(monkeypatch):
    monkeypatch.setenv("KORTEXT_QDRANT_URL", "http://async-env:6333")

    with patch("kortext._qdrant.AsyncQdrantClient") as mock_async_client:
        client = get_async_qdrant_client()
        mock_async_client.assert_called_once_with(url="http://async-env:6333", timeout=5.0)
        assert client == mock_async_client.return_value


def test_get_sync_qdrant_client_returns_qdrant_client(monkeypatch):
    monkeypatch.delenv("KORTEXT_QDRANT_URL", raising=False)
    monkeypatch.delenv("CEREBRUM_QDRANT_URL", raising=False)
    monkeypatch.delenv("QDRANT_URL", raising=False)

    with patch("kortext._qdrant.QdrantClient") as mock_client:
        client = get_sync_qdrant_client()
        mock_client.assert_called_once_with(url="http://localhost:6333", timeout=5.0)
        assert client == mock_client.return_value

    monkeypatch.setenv("QDRANT_URL", "http://env-custom-qdrant:6333")
    with patch("kortext._qdrant.QdrantClient") as mock_client:
        client = get_sync_qdrant_client(timeout=3.5)
        mock_client.assert_called_once_with(url="http://env-custom-qdrant:6333", timeout=3.5)
        assert client == mock_client.return_value


def test_get_async_qdrant_client_configured_for_http_url(monkeypatch):
    monkeypatch.delenv("KORTEXT_QDRANT_URL", raising=False)
    monkeypatch.delenv("CEREBRUM_QDRANT_URL", raising=False)
    monkeypatch.delenv("QDRANT_URL", raising=False)

    with patch("kortext._qdrant.AsyncQdrantClient") as mock_async_client:
        client = get_async_qdrant_client()
        mock_async_client.assert_called_once_with(url="http://localhost:6333", timeout=5.0)
        assert client == mock_async_client.return_value

    monkeypatch.setenv("QDRANT_URL", "http://custom-http:6333")
    with patch("kortext._qdrant.AsyncQdrantClient") as mock_async_client:
        client = get_async_qdrant_client(timeout=4.0)
        mock_async_client.assert_called_once_with(url="http://custom-http:6333", timeout=4.0)
        assert client == mock_async_client.return_value


def test_is_qdrant_online_success():
    with patch("httpx.Client") as mock_http:
        mock_instance = MagicMock()
        mock_response = MagicMock(status_code=200)
        mock_instance.get.return_value = mock_response
        mock_http.return_value.__enter__.return_value = mock_instance

        assert is_qdrant_online("http://localhost:6333") is True


def test_is_qdrant_online_failure():
    with patch("httpx.Client") as mock_http, patch("socket.socket") as mock_socket:
        mock_instance = MagicMock()
        mock_instance.get.side_effect = Exception("Connection refused")
        mock_http.return_value.__enter__.return_value = mock_instance

        mock_sock_inst = MagicMock()
        mock_sock_inst.connect_ex.return_value = 1  # non-zero means failure
        mock_socket.return_value = mock_sock_inst

        assert is_qdrant_online("http://localhost:6333") is False
