"""
Tests verifying decoupling of dashboard circular view bindings, SQLite WAL mode, and dead code removal.
"""
import sqlite3
import sys
from pathlib import Path
import pytest


def test_specs_does_not_import_overview():
    """Ensure specs.py does not import overview.py and has no _bind_specs_handlers."""
    import kortext.dashboard.views.specs as specs

    assert not hasattr(specs, "_bind_specs_handlers"), "specs.py should not have _bind_specs_handlers"

    with open(specs.__file__, "r", encoding="utf-8") as f:
        content = f.read()

    assert "overview" not in content, (
        "specs.py must not contain imports from overview.py"
    )
    assert "_bind_specs_handlers" not in content

    # Check that overview registers the handlers into REL_SPECS
    import kortext.dashboard.views.overview as overview

    for rel in ["DEFINED_IN", "REFERENCES", "IMPORTS", "IMPLEMENTS", "TYPE_OF", "LINKS_TO", "TAG"]:
        assert specs.REL_SPECS[rel]["handler"] is not None, f"Handler for {rel} should be registered by overview"



def test_ingest_cache_wal_and_busy_timeout(tmp_path):
    """Ensure IngestCache sets journal_mode=WAL and busy_timeout=30000."""
    from kortext.cache import IngestCache

    db_file = tmp_path / "test_cache.db"
    cache = IngestCache(db_path=db_file)

    with cache._get_connection() as conn:
        journal_mode = conn.execute("PRAGMA journal_mode;").fetchone()[0]
        busy_timeout = conn.execute("PRAGMA busy_timeout;").fetchone()[0]

    assert journal_mode.lower() == "wal", f"Expected WAL mode, got {journal_mode}"
    assert busy_timeout == 30000, f"Expected busy_timeout 30000, got {busy_timeout}"



def test_chunk_embedding_cache_wal_and_busy_timeout(tmp_path):
    """Ensure ChunkEmbeddingCache sets journal_mode=WAL and busy_timeout=30000."""
    from kortext.cache import ChunkEmbeddingCache

    db_file = tmp_path / "test_embed_cache.db"
    cache = ChunkEmbeddingCache(db_path=db_file)

    with cache._get_connection() as conn:
        journal_mode = conn.execute("PRAGMA journal_mode;").fetchone()[0]
        busy_timeout = conn.execute("PRAGMA busy_timeout;").fetchone()[0]

    assert journal_mode.lower() == "wal", f"Expected WAL mode, got {journal_mode}"
    assert busy_timeout == 30000, f"Expected busy_timeout 30000, got {busy_timeout}"

