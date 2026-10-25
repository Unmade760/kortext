"""
Unit tests for kortext.retrieval.discovery.
Verifies unified Qdrant vector collections discovery across embedded SQLite and remote HTTP modes.
Invariant 3 compliance: Secondary processes NEVER instantiate QdrantClient(path=...).
"""

import json
import sqlite3
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from kortext.retrieval.discovery import discover_vector_collections


def test_discover_embedded_with_sqlite(tmp_path, monkeypatch):
    """Test embedded discovery inspecting meta.json and collection storage.sqlite."""
    qpath = tmp_path / ".kortext" / "qdrant"
    col_dir = qpath / "collection" / "test_docs"
    col_dir.mkdir(parents=True, exist_ok=True)

    meta_file = qpath / "meta.json"
    meta_file.write_text(
        json.dumps({
            "collections": {
                "test_docs": {
                    "vectors": {"text-dense": {"size": 1536, "distance": "Cosine"}}
                }
            }
        }),
        encoding="utf-8",
    )

    sqlite_file = col_dir / "storage.sqlite"
    conn = sqlite3.connect(sqlite_file)
    cur = conn.cursor()
    cur.execute("CREATE TABLE points (id INTEGER PRIMARY KEY, val TEXT)")
    cur.executemany("INSERT INTO points (val) VALUES (?)", [("a",), ("b",), ("c",)])
    conn.commit()
    conn.close()

    monkeypatch.delenv("QDRANT_URL", raising=False)
    monkeypatch.setenv("KORTEXT_HOME", str(tmp_path / ".kortext"))

    cols = discover_vector_collections()
    assert len(cols) == 1
    assert cols[0]["name"] == "test_docs"
    assert cols[0]["status"] == "embedded"
    assert cols[0]["points_count"] == 3
    assert cols[0]["vectors_count"] == 3
    assert cols[0]["engine"] == "RocksDB (Rust)"
    assert "vectors_config" in cols[0]


def test_discover_embedded_missing_meta(tmp_path, monkeypatch):
    """Test embedded discovery returns empty list when meta.json does not exist."""
    monkeypatch.delenv("QDRANT_URL", raising=False)
    monkeypatch.setenv("KORTEXT_HOME", str(tmp_path / "nonexistent"))

    cols = discover_vector_collections()
    assert cols == []


def test_discover_embedded_fallback_metadata_count(tmp_path, monkeypatch):
    """Test embedded discovery falls back to meta.json points_count when sqlite is absent."""
    qpath = tmp_path / ".kortext" / "qdrant"
    qpath.mkdir(parents=True, exist_ok=True)
    meta_file = qpath / "meta.json"
    meta_file.write_text(
        json.dumps({
            "collections": {
                "sparse_col": {
                    "points_count": 99,
                    "vectors": None,
                }
            }
        }),
        encoding="utf-8",
    )
    monkeypatch.delenv("QDRANT_URL", raising=False)
    monkeypatch.setenv("KORTEXT_HOME", str(tmp_path / ".kortext"))

    cols = discover_vector_collections()
    assert len(cols) == 1
    assert cols[0]["name"] == "sparse_col"
    assert cols[0]["points_count"] == 99


def test_discover_remote_http_success(monkeypatch):
    """Test remote HTTP discovery with mocked httpx.Client."""
    monkeypatch.setenv("QDRANT_URL", "http://localhost:6333")

    with patch("httpx.Client") as mock_client_cls:
        mock_client = MagicMock()
        mock_resp_cols = MagicMock()
        mock_resp_cols.status_code = 200
        mock_resp_cols.json.return_value = {
            "result": {"collections": [{"name": "knowledge_col"}]}
        }
        mock_resp_info = MagicMock()
        mock_resp_info.status_code = 200
        mock_resp_info.json.return_value = {
            "result": {
                "points_count": 100,
                "vectors_count": 100,
                "indexed_vectors_count": 100,
                "status": "green",
                "config": {"params": {"vectors": {"size": 384, "distance": "Cosine"}}},
            }
        }

        def fake_get(url):
            if url.endswith("/collections"):
                return mock_resp_cols
            return mock_resp_info

        mock_client.get = MagicMock(side_effect=fake_get)
        mock_client.__enter__.return_value = mock_client
        mock_client.__exit__.return_value = None
        mock_client_cls.return_value = mock_client

        cols = discover_vector_collections()
        assert len(cols) == 1
        assert cols[0]["name"] == "knowledge_col"
        assert cols[0]["points_count"] == 100
        assert cols[0]["status"] == "green"
        assert cols[0]["vectors_config"] == {"size": 384, "distance": "Cosine"}

        # Verify URL was normalized to 127.0.0.1
        called_url = mock_client.get.call_args_list[0][0][0]
        assert "://127.0.0.1:6333" in called_url


def test_discover_remote_http_error(monkeypatch):
    """Test remote HTTP discovery raises when endpoint returns non-200."""
    monkeypatch.delenv("QDRANT_URL", raising=False)

    with patch("httpx.Client") as mock_client_cls:
        mock_client = MagicMock()
        mock_resp = MagicMock()
        mock_resp.status_code = 503
        mock_resp.text = "Service Unavailable"
        mock_client.get.return_value = mock_resp
        mock_client.__enter__.return_value = mock_client
        mock_client.__exit__.return_value = None
        mock_client_cls.return_value = mock_client

        with pytest.raises(RuntimeError, match="503"):
            discover_vector_collections("http://127.0.0.1:6333")
