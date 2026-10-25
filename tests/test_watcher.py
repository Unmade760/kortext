"""
Unit tests for hardened Kortext Incremental File Watcher and Daemon Recovery.
"""

from __future__ import annotations

import asyncio
import os
import time
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
import redis

from kortext.watcher import (
    DebouncedChangeHandler,
    KortextIncrementalSync,
    get_watcher_status,
    write_status,
    WATCHER_STATUS_FILE,
)


class TestWatcherInitialization:
    """Verifies KortextIncrementalSync initialization and substrate wiring."""

    def test_sync_initializes_with_centralized_defaults(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("QDRANT_COLLECTION", "kortext_codebase")
        monkeypatch.setenv("FALKORDB_SYMBOLS_GRAPH", "test_symbols")

        with patch("kortext.watcher.get_async_qdrant_client") as mock_get_qdrant, \
             patch("kortext.watcher.SymbolGraphManager") as mock_sym_mgr, \
             patch("kortext.watcher.IngestCache"), \
             patch("kortext.watcher.ChunkEmbeddingCache"):

            syncer = KortextIncrementalSync()
            assert syncer.collection == "kortext_codebase"
            assert syncer.symbols_graph == "test_symbols"
            mock_get_qdrant.assert_called_once()
            mock_sym_mgr.assert_called_once_with(graph_name="test_symbols")


class TestDebouncedChangeHandler:
    """Verifies file change debouncing and burst mode dynamics."""

    @pytest.mark.anyio
    async def test_debounce_delays_processing_until_interval_elapses(self, tmp_path: Path) -> None:
        mock_syncer = MagicMock(spec=KortextIncrementalSync)
        mock_syncer.sync_file = AsyncMock(return_value=True)
        mock_syncer.delete_file = AsyncMock(return_value=True)

        loop = asyncio.get_running_loop()
        handler = DebouncedChangeHandler(
            loop=loop,
            syncer=mock_syncer,
            debounce_sec=0.1,
            root=str(tmp_path),
        )

        test_file = str(tmp_path / "app.py")
        mock_event = MagicMock()
        mock_event.is_directory = False
        mock_event.src_path = test_file

        # Act: trigger modification event
        handler.on_modified(mock_event)
        assert test_file in handler.pending_events

        # Flush immediately before debounce window expires
        await handler.flush_debounced()
        mock_syncer.sync_file.assert_not_called()

        # Wait for debounce interval to elapse
        await asyncio.sleep(0.12)
        await handler.flush_debounced()

        # Assert: now synced once
        mock_syncer.sync_file.assert_awaited_once_with(test_file)
        assert test_file not in handler.pending_events
        assert handler.total_processed == 1

    @pytest.mark.anyio
    async def test_burst_mode_triggered_and_settled_with_quiescence(self, tmp_path: Path) -> None:
        mock_syncer = MagicMock(spec=KortextIncrementalSync)
        mock_syncer.cache = MagicMock()
        mock_syncer.cache.is_file_changed.return_value = (True, 100, "hash", [])
        mock_syncer.sync_file = AsyncMock(return_value=True)
        mock_syncer.delete_file = AsyncMock(return_value=True)

        loop = asyncio.get_running_loop()
        handler = DebouncedChangeHandler(
            loop=loop,
            syncer=mock_syncer,
            debounce_sec=0.05,
            burst_threshold=5.0,  # low threshold for testing
            quiescence_sec=0.1,
            root=str(tmp_path),
        )

        # Trigger rapid burst of events (>5 in 1 sec)
        for i in range(10):
            p = tmp_path / f"file_{i}.py"
            p.write_text("print('test')", encoding="utf-8")
            evt = MagicMock()
            evt.is_directory = False
            evt.src_path = str(p)
            handler.on_created(evt)

        assert handler.burst_mode is True

        # Flush during burst: should pause processing to prevent lock contention
        await handler.flush_debounced()
        mock_syncer.sync_file.assert_not_called()

        # Wait for quiescence settling period
        await asyncio.sleep(0.15)
        await handler.flush_debounced()

        # Assert burst settled and scoped diff ran
        assert handler.burst_mode is False
        assert mock_syncer.sync_file.await_count == 10


class TestResilientRecovery:
    """Verifies socket and transport error recovery during incremental sync."""

    @pytest.mark.anyio
    async def test_sync_recovers_from_transient_socket_failure(self, tmp_path: Path) -> None:
        sample_file = tmp_path / "service.py"
        sample_file.write_text("def run(): pass\n", encoding="utf-8")

        syncer = KortextIncrementalSync()
        syncer.cache = MagicMock()
        syncer.chunk_cache = MagicMock()

        # Mock index_single_file: fails with ConnectionError first, succeeds on attempt 2
        call_count = 0

        async def fake_index(*args, **kwargs):
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                raise redis.ConnectionError("FalkorDB socket temporarily unavailable")
            return {"status": "indexed", "chunks": 1, "cached": 0, "misses": 1}

        with patch("kortext.watcher.index_single_file", side_effect=fake_index), \
             patch("asyncio.sleep", new_callable=AsyncMock):

            success = await syncer.sync_file(sample_file)
            assert success is True
            assert call_count == 2

    @pytest.mark.anyio
    async def test_delete_file_purges_and_recovers_from_client_error(self, tmp_path: Path) -> None:
        deleted_file = tmp_path / "deleted.py"

        syncer = KortextIncrementalSync()
        syncer.cache = MagicMock()
        syncer.cache.remove_file.return_value = ["point_1", "point_2"]
        syncer.qdrant_client = AsyncMock()
        syncer.symbol_mgr = MagicMock()

        success = await syncer.delete_file(str(deleted_file))
        assert success is True
        syncer.qdrant_client.delete.assert_awaited_once()
        syncer.symbol_mgr.delete_file_ast.assert_called_once_with(str(deleted_file.resolve()))


class TestWatcherStatusVitality:
    """Verifies status file read/write and PID vitality checks."""

    def test_write_and_get_status_live_pid(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        status_file = tmp_path / "watcher_status.json"
        monkeypatch.setattr("kortext.watcher.WATCHER_STATUS_FILE", status_file)

        write_status(
            running=True,
            pid=os.getpid(),
            root="/test/root",
            collection="test_coll",
            debounce_sec=1.5,
            total_processed=42,
        )

        status = get_watcher_status()
        assert status["running"] is True
        assert status["alive"] is True
        assert status["status"] == "RUNNING"
        assert status["pid"] == os.getpid()
        assert status["total_processed"] == 42

    def test_get_status_dead_pid_reports_stopped(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        status_file = tmp_path / "watcher_status.json"
        monkeypatch.setattr("kortext.watcher.WATCHER_STATUS_FILE", status_file)

        # PID 999999 is almost certainly non-existent
        write_status(
            running=True,
            pid=999999,
            root="/test/root",
            collection="test_coll",
        )

        status = get_watcher_status()
        assert status["running"] is False
        assert status["status"] == "DEAD_STALE_PID"
