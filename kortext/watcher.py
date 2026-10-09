"""
Kortext Automated Incremental File Watcher.
Monitors project directories using watchdog, debouncing file modification events
and incrementally synchronizing Qdrant vectors and FalkorDB symbol graphs in near real-time.
Leverages ChunkEmbeddingCache to make single-file re-indexing sub-second.
"""

from __future__ import annotations

import argparse
import asyncio
import fnmatch
import json
import logging
import os
import signal
import sys
import time
from collections import deque
from pathlib import Path
from typing import Any, Dict, List, Optional, Set
import warnings

import httpx
from dotenv import load_dotenv
from llama_index.core.schema import Document
from qdrant_client import AsyncQdrantClient
from qdrant_client import models as qmodels
from watchdog.events import FileSystemEvent, FileSystemEventHandler
from watchdog.observers import Observer

from kortext.cache import ChunkEmbeddingCache, IngestCache
from kortext.ingest import DEFAULT_EXCLUDE, SUPPORTED_EXT, index_single_file
from kortext.symbols import SymbolGraphManager
from kortext.chunking.ast_splitter import ASTCodeSplitter, LANG_MAP

load_dotenv()

logger = logging.getLogger("kortext.watcher")

EMBED_BASE_URL = os.getenv("EMBED_BASE_URL", "http://localhost:8000/v1").replace("://localhost", "://127.0.0.1")
EMBED_MODEL_NAME = os.getenv("EMBED_MODEL_NAME", "mlx-community--Qwen3-Embedding-8B-4bit-DWQ")
QDRANT_URL = os.getenv("QDRANT_URL", "http://localhost:6333").replace("://localhost", "://127.0.0.1")


from kortext._home import KORTEXT_HOME

CEREBRUM_HOME = KORTEXT_HOME
COLLECTION = os.getenv("KORTEXT_COLLECTION", os.getenv("QDRANT_COLLECTION", "kortext_codebase"))
DEFAULT_DEBOUNCE = float(os.getenv("KORTEXT_WATCH_DEBOUNCE", os.getenv("CEREBRUM_WATCH_DEBOUNCE", "2.0")))
WATCHER_STATUS_FILE = Path(os.getenv("KORTEXT_WATCHER_STATUS", os.getenv("CEREBRUM_WATCHER_STATUS", str(KORTEXT_HOME / "watcher_status.json"))))

DEFAULT_EXCLUDE_DIRS: List[str] = list(
    dict.fromkeys(
        [
            ".git",
            "node_modules",
            "__pycache__",
            ".venv",
            "venv",
            "dist",
            "build",
            ".pytest_cache",
            ".gemini",
            "*.min.js",
            "*.pyc",
            "*.lock",
            "*.map",
        ]
        + [x for x in DEFAULT_EXCLUDE if x]
    )
)
DEFAULT_WATCHER_EXCLUDE = DEFAULT_EXCLUDE_DIRS


def write_status(
    running: bool,
    pid: Optional[int] = None,
    root: Optional[str] = None,
    collection: Optional[str] = None,
    debounce_sec: Optional[float] = None,
    total_processed: int = 0,
    last_event_time: Optional[float] = None,
    last_synced_file: Optional[str] = None,
    pending_count: int = 0,
    burst_mode: bool = False,
    event_rate: float = 0.0,
):
    """Persists watcher lifecycle and telemetry to status file."""
    try:
        WATCHER_STATUS_FILE.parent.mkdir(parents=True, exist_ok=True)
        data = {
            "running": running,
            "pid": pid or os.getpid(),
            "root": root,
            "collection": collection,
            "debounce_sec": debounce_sec,
            "total_processed": total_processed,
            "last_event_time": last_event_time,
            "last_synced_file": last_synced_file,
            "pending_count": pending_count,
            "burst_mode": burst_mode,
            "event_rate": event_rate,
            "timestamp": time.time(),
        }
        with open(WATCHER_STATUS_FILE, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2)
    except Exception:
        pass


def get_watcher_status() -> Dict[str, Any]:
    """Reads live watcher status, checking PID vitality."""
    if not WATCHER_STATUS_FILE.exists():
        return {"running": False, "status": "STOPPED", "message": "Watcher daemon not started"}
    try:
        with open(WATCHER_STATUS_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)
        pid = data.get("pid")
        if not data.get("running") or not pid:
            return {"running": False, "status": "STOPPED", **data}
        try:
            os.kill(pid, 0)
            data["alive"] = True
            data["status"] = "RUNNING"
        except OSError:
            data["alive"] = False
            data["running"] = False
            data["status"] = "DEAD_STALE_PID"
        return data
    except Exception as exc:
        return {"running": False, "status": "ERROR", "error": str(exc)}


class KortextIncrementalSync:
    """Performs single-file incremental updates across Qdrant, Chunk Cache, and FalkorDB."""

    def __init__(
        self,
        collection: str = COLLECTION,
        symbols_graph: Optional[str] = None,
        embed_model_name: str = EMBED_MODEL_NAME,
        embed_base_url: str = EMBED_BASE_URL,
        qdrant_url: str = QDRANT_URL,
    ):
        self.collection = collection
        default_sym = os.getenv("KORTEXT_SYMBOLS_GRAPH", os.getenv("FALKORDB_SYMBOLS_GRAPH", "kortext_symbols"))
        self.symbols_graph = symbols_graph or (
            f"{collection}_symbols" if collection not in ("kortext_codebase", "cerebrum_codebase") else default_sym
        )
        self.embed_model_name = embed_model_name
        self.embed_base_url = embed_base_url.replace("://localhost", "://127.0.0.1") if embed_base_url else embed_base_url
        self.qdrant_url = qdrant_url.replace("://localhost", "://127.0.0.1") if qdrant_url else qdrant_url

        self.cache = IngestCache()
        self.chunk_cache = ChunkEmbeddingCache()
        self.symbol_mgr = SymbolGraphManager(graph_name=self.symbols_graph)

        self.qdrant_client = AsyncQdrantClient(url=self.qdrant_url)

    async def _process_file_event(self, file_path: str | Path, force: bool = False) -> bool:
        """Incrementally syncs a created or modified file delegating to index_single_file."""
        p = Path(file_path).resolve()
        start_t = time.perf_counter()

        if not p.exists():
            return await self.delete_file(str(p))

        res = await index_single_file(
            file_path=p,
            collection=self.collection,
            target_symbols_db=self.symbols_graph,
            force=force,
            client=self.qdrant_client,
            cache=self.cache,
            chunk_cache=self.chunk_cache,
            symbol_mgr=self.symbol_mgr,
        )

        if res.get("status") == "skipped":
            return False

        if res.get("status") == "error":
            logger.warning(f"[Kortext Watcher] ⚠️  Error syncing '{p.name}': {res.get('error')}")
            return False

        duration = time.perf_counter() - start_t
        chunks = res.get("chunks", 0)
        cached = res.get("cached", 0)
        misses = res.get("misses", 0)
        hit_pct = round((cached / (cached + misses)) * 100, 1) if (cached + misses) > 0 else 0.0
        logger.info(
            f"[Kortext Watcher] ⚡ Synced '{p.name}' in {duration:.3f}s "
            f"({chunks} chunks, {cached} cached [{hit_pct}%], {misses} new vectors)"
        )
        return True

    sync_file = _process_file_event


    async def delete_file(self, file_path: str) -> bool:
        """Purges a deleted file from Qdrant, Cache, and FalkorDB."""
        p = Path(file_path).resolve()
        resolved_fp = str(p)

        old_points = self.cache.remove_file(resolved_fp, self.collection)
        if old_points:
            try:
                await self.qdrant_client.delete(
                    collection_name=self.collection,
                    points_selector=qmodels.PointIdsList(points=old_points),
                )
            except Exception:
                pass

        # Purge File node, Section nodes, ghost CALLS edges, and orphaned Symbols in FalkorDB
        try:
            self.symbol_mgr.delete_file_ast(resolved_fp)
        except Exception:
            pass

        logger.info(f"[Kortext Watcher] 🗑️  Purged deleted file '{p.name}' from vector index and AST symbol graph.")
        return True


class CerebrumIncrementalSync(KortextIncrementalSync):
    """Deprecated alias for KortextIncrementalSync."""

    def __init__(self, *args, **kwargs):
        warnings.warn(
            "CerebrumIncrementalSync is deprecated, use KortextIncrementalSync instead.",
            DeprecationWarning,
            stacklevel=2,
        )
        super().__init__(*args, **kwargs)


CortexIncrementalSync = KortextIncrementalSync  # Backwards compatibility alias
IncrementalSync = KortextIncrementalSync
FileWatcher = KortextIncrementalSync


class DebouncedChangeHandler(FileSystemEventHandler):
    """Gathers filesystem events and queues them with an adaptive burst debouncer."""

    def __init__(
        self,
        loop: asyncio.AbstractEventLoop,
        syncer: KortextIncrementalSync,
        debounce_sec: float = 2.0,
        root: str = "",
        collection: str = "",
        burst_threshold: float = 15.0,
        quiescence_sec: float = 2.0,
        exclude_dirs: Optional[List[str] | Set[str]] = None,
    ):
        self.loop = loop
        self.syncer = syncer
        self.debounce_sec = debounce_sec
        self.root = root
        self.collection = collection
        self.burst_threshold = burst_threshold
        self.quiescence_sec = quiescence_sec
        self.exclude_dirs: List[str] = list(exclude_dirs) if exclude_dirs is not None else list(DEFAULT_EXCLUDE_DIRS)

        self.pending_events: Dict[str, float] = {}  # file_path -> last_event_time
        self.deleted_events: Set[str] = set()
        self.total_processed: int = 0
        self.last_event_time: Optional[float] = None
        self.last_synced_file: Optional[str] = None
        self._lock = asyncio.Lock()
        self._last_status_write = 0.0

        # Burst debouncing state (>15 files/sec)
        self._recent_event_times: deque = deque()
        self.burst_mode: bool = False
        self.burst_start_time: Optional[float] = None
        self.last_burst_event_time: Optional[float] = None
        self.current_event_rate: float = 0.0

    def _should_ignore(self, path: str | Path) -> bool:
        p = Path(path)
        # Check extensions
        if p.is_file() and p.suffix.lower() not in SUPPORTED_EXT:
            return True
        name = p.name
        path_str = str(p)
        for ex in self.exclude_dirs:
            clean_ex = ex.strip("*/")
            # Directory or exact part match
            if clean_ex and clean_ex in p.parts:
                return True
            # Glob filename match
            if fnmatch.fnmatch(name, ex) or (clean_ex and fnmatch.fnmatch(name, f"*{clean_ex}*")):
                return True
            # Path match
            try:
                if fnmatch.fnmatch(path_str, ex) or p.match(ex):
                    return True
            except Exception:
                if fnmatch.fnmatch(path_str, ex):
                    return True
        return False

    def _record_event(self, path: str, is_deleted: bool = False, dest_path: Optional[str] = None):
        """Tracks event rate and manages adaptive burst mode transition."""
        now = time.time()
        self.last_event_time = now
        self._recent_event_times.append(now)

        # Sliding window of events in last 1.0 second
        cutoff = now - 1.0
        while self._recent_event_times and self._recent_event_times[0] < cutoff:
            self._recent_event_times.popleft()

        self.current_event_rate = float(len(self._recent_event_times))

        # Check burst trigger threshold
        if self.current_event_rate > self.burst_threshold:
            if not self.burst_mode:
                self.burst_mode = True
                self.burst_start_time = now
                logger.warning(
                    f"[Kortext Watcher] High event frequency ({self.current_event_rate:.1f} events/s > {self.burst_threshold}/s). "
                    f"Entering burst mode: pausing incremental graph updates to prevent lock thrashing."
                )
            self.last_burst_event_time = now

        if is_deleted:
            self.deleted_events.add(path)
            self.pending_events.pop(path, None)
        else:
            self.pending_events[path] = now

        if dest_path:
            self.pending_events[dest_path] = now

    def on_created(self, event: FileSystemEvent):
        if not event.is_directory and not self._should_ignore(event.src_path):
            self._record_event(event.src_path, is_deleted=False)

    def on_modified(self, event: FileSystemEvent):
        if not event.is_directory and not self._should_ignore(event.src_path):
            self._record_event(event.src_path, is_deleted=False)

    def on_deleted(self, event: FileSystemEvent):
        if not event.is_directory and not self._should_ignore(event.src_path):
            self._record_event(event.src_path, is_deleted=True)

    def on_moved(self, event: FileSystemEvent):
        if not event.is_directory:
            src_ignored = self._should_ignore(event.src_path)
            dest_ignored = self._should_ignore(event.dest_path)
            if not src_ignored and not dest_ignored:
                self._record_event(event.src_path, is_deleted=True, dest_path=event.dest_path)
            elif not src_ignored:
                self._record_event(event.src_path, is_deleted=True)
            elif not dest_ignored:
                self._record_event(event.dest_path, is_deleted=False)

    async def _execute_burst_scoped_diff(self):
        """Executes a scoped diff scan across the gathered files after a burst settling period."""
        # 1. Process deletions
        deleted_paths = list(self.deleted_events)
        self.deleted_events.clear()
        for path_str in deleted_paths:
            try:
                await self.syncer.delete_file(path_str)
                self.total_processed += 1
                self.last_synced_file = path_str
            except Exception as exc:
                logger.error(f"[Kortext Watcher] Error purging {path_str} during burst diff: {exc}")

        # 2. Process modified/created files with fast cache diff
        candidate_paths = list(self.pending_events.keys())
        self.pending_events.clear()

        synced_count = 0
        skipped_count = 0
        for path_str in candidate_paths:
            p = Path(path_str)
            if not p.exists():
                try:
                    await self.syncer.delete_file(path_str)
                    self.total_processed += 1
                except Exception:
                    pass
                continue

            changed, _, _, _ = self.syncer.cache.is_file_changed(str(p.resolve()), self.collection)
            if changed:
                try:
                    if await self.syncer.sync_file(path_str):
                        self.total_processed += 1
                        self.last_synced_file = path_str
                        synced_count += 1
                except Exception as exc:
                    logger.error(f"[Kortext Watcher] Error syncing {path_str} during burst diff: {exc}")
            else:
                skipped_count += 1

        logger.info(
            f"[Kortext Watcher] Scoped diff scan complete: {synced_count} files synchronized, "
            f"{len(deleted_paths)} purged, {skipped_count} unchanged skipped."
        )

    async def flush_debounced(self):
        """Periodically flushes debounced items, or performs scoped diff scan if recovering from burst mode."""
        now = time.time()

        # Check burst settling
        if self.burst_mode:
            silence_duration = now - (self.last_burst_event_time or now)
            if silence_duration < self.quiescence_sec:
                # Still in settling period, wait for quiescence
                if now - self._last_status_write > 1.0:
                    self._last_status_write = now
                    write_status(
                        running=True,
                        pid=os.getpid(),
                        root=self.root,
                        collection=self.collection,
                        debounce_sec=self.debounce_sec,
                        total_processed=self.total_processed,
                        last_event_time=self.last_event_time,
                        last_synced_file=self.last_synced_file,
                        pending_count=len(self.pending_events) + len(self.deleted_events),
                        burst_mode=True,
                        event_rate=self.current_event_rate,
                    )
                return

            # Settled after burst
            logger.info(f"[Kortext Watcher] Burst activity settled after {silence_duration:.2f}s quiescence. Executing scoped diff scan...")
            await self._execute_burst_scoped_diff()
            self.burst_mode = False
            self.burst_start_time = None
            self.last_burst_event_time = None
            return

        to_process = []
        for path_str, last_t in list(self.pending_events.items()):
            if now - last_t >= self.debounce_sec:
                to_process.append(path_str)
                del self.pending_events[path_str]

        # Process deletions
        for path_str in list(self.deleted_events):
            self.deleted_events.remove(path_str)
            try:
                await self.syncer.delete_file(path_str)
                self.total_processed += 1
                self.last_synced_file = path_str
            except Exception as exc:
                logger.error(f"[Kortext Watcher] Error purging {path_str}: {exc}")

        # Process modifications / creations
        for path_str in to_process:
            try:
                synced = await self.syncer.sync_file(path_str)
                if synced:
                    self.total_processed += 1
                    self.last_synced_file = path_str
            except Exception as exc:
                logger.error(f"[Kortext Watcher] Error syncing {path_str}: {exc}")

        if now - self._last_status_write > 2.0 or to_process:
            self._last_status_write = now
            write_status(
                running=True,
                pid=os.getpid(),
                root=self.root,
                collection=self.collection,
                debounce_sec=self.debounce_sec,
                total_processed=self.total_processed,
                last_event_time=self.last_event_time,
                last_synced_file=self.last_synced_file,
                pending_count=len(self.pending_events) + len(self.deleted_events),
                burst_mode=self.burst_mode,
                event_rate=self.current_event_rate,
            )



async def start_watcher(
    watch_root: str,
    collection: str = COLLECTION,
    debounce_sec: float = DEFAULT_DEBOUNCE,
    exclude_dirs: Optional[List[str] | Set[str]] = None,
):
    """Starts the background directory observer and debounced flush loop."""
    root_path = Path(watch_root).resolve()
    logger.info(f"[Kortext Watcher] 👁️  Starting file watcher on: {root_path}")
    logger.info(f"[Kortext Watcher] Collection: {collection} | Debounce window: {debounce_sec}s")

    syncer = KortextIncrementalSync(collection=collection)
    loop = asyncio.get_running_loop()
    handler = DebouncedChangeHandler(
        loop=loop,
        syncer=syncer,
        debounce_sec=debounce_sec,
        root=str(root_path),
        collection=collection,
        exclude_dirs=exclude_dirs,
    )

    write_status(
        running=True,
        pid=os.getpid(),
        root=str(root_path),
        collection=collection,
        debounce_sec=debounce_sec,
        total_processed=0,
        pending_count=0,
    )

    observer = Observer()
    observer.schedule(handler, str(root_path), recursive=True)
    observer.start()

    stop_event = asyncio.Event()

    def _on_stop():
        logger.info("[Kortext Watcher] Stopping watcher...")
        observer.stop()
        stop_event.set()

    try:
        loop.add_signal_handler(signal.SIGINT, _on_stop)
        loop.add_signal_handler(signal.SIGTERM, _on_stop)
    except (NotImplementedError, RuntimeError):
        pass

    try:
        while not stop_event.is_set():
            await handler.flush_debounced()
            await asyncio.sleep(0.5)
    finally:
        observer.stop()
        observer.join()
        write_status(
            running=False,
            pid=os.getpid(),
            root=str(root_path),
            collection=collection,
            debounce_sec=debounce_sec,
            total_processed=handler.total_processed,
            last_event_time=handler.last_event_time,
            last_synced_file=handler.last_synced_file,
            pending_count=0,
        )
        logger.info("[Kortext Watcher] Watcher stopped cleanly.")


def main():
    parser = argparse.ArgumentParser(description="Kortext Incremental Real-Time File Watcher")
    parser.add_argument("--root", default=".", help="Directory to monitor (default: current directory)")
    parser.add_argument("--collection", default=COLLECTION, help="Qdrant collection name")
    parser.add_argument("--debounce", type=float, default=DEFAULT_DEBOUNCE, help="Debounce seconds (default: 2.0)")
    args = parser.parse_args()

    asyncio.run(start_watcher(watch_root=args.root, collection=args.collection, debounce_sec=args.debounce))


if __name__ == "__main__":
    main()
