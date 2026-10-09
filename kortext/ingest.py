"""
Batch ingestor: reads files from a directory tree and indexes them into Qdrant.
Optimized for high-throughput embedding on Apple Silicon Metal with concurrent batch evaluation
and Content-Hash Incremental Ingestion to skip unchanged files.

Usage:
  cerebrum-ingest --root /path/to/project [--collection my_collection] [--force]
"""
import argparse
import asyncio
import logging
import os
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional, Set

import httpx
from dotenv import load_dotenv
from llama_index.core import Settings, SimpleDirectoryReader, StorageContext, VectorStoreIndex
from llama_index.embeddings.openai import OpenAIEmbedding
from llama_index.vector_stores.qdrant import QdrantVectorStore
from qdrant_client import AsyncQdrantClient, QdrantClient
from qdrant_client import models as qmodels

from kortext.cache import IngestCache, ChunkEmbeddingCache

try:
    from fastembed import SparseTextEmbedding
    TextSparseModel = SparseTextEmbedding
except ImportError:
    SparseTextEmbedding = None  # type: ignore
    TextSparseModel = None      # type: ignore

_SPARSE_MODEL: Optional[Any] = None


def get_sparse_model() -> Optional[Any]:
    """Lazily initializes and returns singleton TextSparseModel for BM25 sparse vectors."""
    global _SPARSE_MODEL
    if _SPARSE_MODEL is None and TextSparseModel is not None:
        try:
            _SPARSE_MODEL = TextSparseModel(model_name="Qdrant/bm25")
        except Exception as exc:
            logger.warning(f"[Kortext Ingest] Failed to initialize sparse model: {exc}")
    return _SPARSE_MODEL

load_dotenv()

logger = logging.getLogger(__name__)

EMBED_BASE_URL  = os.getenv("EMBED_BASE_URL", "http://localhost:8000/v1").replace("://localhost", "://127.0.0.1")
QDRANT_URL      = os.getenv("QDRANT_URL", "http://localhost:6333").replace("://localhost", "://127.0.0.1")
COLLECTION      = os.getenv("KORTEXT_COLLECTION", os.getenv("QDRANT_COLLECTION", "kortext_codebase"))
DEFAULT_SYMBOLS_GRAPH = os.getenv("KORTEXT_SYMBOLS_GRAPH", os.getenv("FALKORDB_SYMBOLS_GRAPH", "kortext_symbols"))
DEFAULT_EXCLUDE = os.getenv(
    "INGEST_EXCLUDE_PATTERNS",
    ".git,node_modules,__pycache__,.venv,dist,build,*.gguf,*.pyc,*.log,*.lock,.DS_Store,coverage/,target/,*.min.js,vendor,vendors,third_party,extern,deps",
).split(",")
MAX_FILE_SIZE_BYTES = int(os.getenv("MAX_FILE_SIZE_BYTES", str(2 * 1024 * 1024)))  # 2MB ceiling

from kortext.chunking.languages import ALL_SUPPORTED_EXTS

SUPPORTED_EXT = ALL_SUPPORTED_EXTS


async def index_single_file(
    file_path: Path,
    collection: str = COLLECTION,
    target_symbols_db: str = DEFAULT_SYMBOLS_GRAPH,
    root: Optional[Path] = None,
    force: bool = False,
    client: Optional[AsyncQdrantClient] = None,
    cache: Optional[IngestCache] = None,
    chunk_cache: Optional[ChunkEmbeddingCache] = None,
    symbol_mgr: Optional[Any] = None,
    sparse_model: Optional[Any] = None,
) -> Dict[str, Any]:
    """
    Indexes a single file: cleans old points from Qdrant, extracts AST symbols/markdown
    into FalkorDB, and chunks & upserts vector points into Qdrant.
    """
    p = Path(file_path).resolve()
    resolved_fp = str(p)

    if not p.exists() or not p.is_file():
        return {
            "status": "error",
            "error": f"File does not exist: {file_path}",
            "file_path": resolved_fp,
            "chunks": 0,
            "symbols": 0,
            "points": [],
            "cached": 0,
            "misses": 0,
            "changed": False,
        }

    if cache is None:
        cache = IngestCache()
    if client is None:
        client = AsyncQdrantClient(url=QDRANT_URL)
    if chunk_cache is None:
        chunk_cache = ChunkEmbeddingCache()
    if symbol_mgr is None:
        from kortext.symbols import SymbolGraphManager
        symbol_mgr = SymbolGraphManager(graph_name=target_symbols_db)

    # Guardrail: Check file size ceiling
    try:
        st = p.stat()
        if st.st_size > MAX_FILE_SIZE_BYTES:
            logger.warning(f"[Kortext Ingest] ⚠️  Skipping large file {p.name} ({st.st_size} bytes > {MAX_FILE_SIZE_BYTES})")
            return {
                "status": "skipped",
                "reason": "file_too_large",
                "file_path": resolved_fp,
                "chunks": 0,
                "symbols": 0,
                "points": [],
                "cached": 0,
                "misses": 0,
                "changed": False,
            }
    except Exception:
        pass

    # Guardrail: Binary detection
    try:
        with open(p, "rb") as bf:
            header = bf.read(8192)
            if b"\x00" in header:
                logger.debug(f"[Kortext Ingest] Skipping binary file: {p.name}")
                return {
                    "status": "skipped",
                    "reason": "binary_file",
                    "file_path": resolved_fp,
                    "chunks": 0,
                    "symbols": 0,
                    "points": [],
                    "cached": 0,
                    "misses": 0,
                    "changed": False,
                }
    except Exception as exc:
        pass

    # 1. Content-Hash Incremental Ingestion Check
    if force:
        changed = True
        mtime, sha = IngestCache.get_file_stats(p)
        old_points = cache.get_all_cached_files(collection).get(resolved_fp, [])
    else:
        changed, mtime, sha, old_points = cache.is_file_changed(resolved_fp, collection)

    if not changed:
        return {
            "status": "skipped",
            "file_path": resolved_fp,
            "chunks": 0,
            "symbols": 0,
            "points": old_points,
            "cached": 0,
            "misses": 0,
            "changed": False,
        }

    # 2. Read file content
    try:
        with open(p, "r", encoding="utf-8", errors="replace") as f:
            content = f.read()
    except Exception as exc:
        logger.warning(f"[Kortext Ingest] ⚠️  Cannot read {p.name}: {exc}")
        return {
            "status": "error",
            "error": str(exc),
            "file_path": resolved_fp,
            "chunks": 0,
            "symbols": 0,
            "points": [],
            "cached": 0,
            "misses": 0,
            "changed": True,
        }

    # 3. Clean old points from Qdrant before upserting new ones
    if old_points:
        try:
            await client.delete(
                collection_name=collection,
                points_selector=qmodels.PointIdsList(points=old_points),
            )
        except Exception as exc:
            logger.debug(f"[Kortext Ingest] Old points deletion notice for {resolved_fp}: {exc}")

    # 4. Extract AST symbols or markdown into FalkorDB
    from kortext.symbols import MarkdownSymbolExtractor
    from kortext.chunking.ast_splitter import LANG_MAP, ASTCodeSplitter

    ext = p.suffix.lower()
    symbol_count = 0
    ref_count = 0
    tree = None
    source_bytes = None
    ast_info = None

    if ext in LANG_MAP:
        try:
            splitter = ASTCodeSplitter(language=LANG_MAP[ext])
            source_bytes = content.encode("utf-8")
            tree = splitter.parser.parse(source_bytes) if hasattr(splitter, "parser") else None
            ast_info = splitter.extract_symbols_and_references(
                content, file_path=resolved_fp, tree=tree, source_bytes=source_bytes
            )
            decls = ast_info.get("declarations", [])
            imports = ast_info.get("imports", [])
            refs = ast_info.get("references", [])
            symbol_mgr.save_file_ast(
                file_path=resolved_fp,
                declarations=decls,
                imports=imports,
                references=refs,
            )
            symbol_count = len(decls)
            ref_count = len(refs)
        except Exception as exc:
            logger.warning(f"[Kortext Ingest] ⚠️  Symbol extraction error on {p.name}: {exc}")
    elif ext in (".md", ".markdown"):
        try:
            md_ext = MarkdownSymbolExtractor(workspace_root=str(root) if root else str(p.parent))
            md_info = md_ext.extract(content, file_path=resolved_fp)
            symbol_mgr.save_markdown_ast(
                file_path=md_info["file_path"],
                title=md_info["title"],
                frontmatter=md_info["frontmatter"],
                sections=md_info["sections"],
                declarations=md_info["declarations"],
                links=md_info["links"],
                tags=md_info["tags"],
            )
            symbol_count = len(md_info.get("declarations", []))
        except Exception as exc:
            logger.warning(f"[Kortext Ingest] ⚠️  Markdown extraction error on {p.name}: {exc}")

    # 5. AST-aware chunking
    from kortext.chunking import SmartCodeNodeParser
    from llama_index.core.schema import Document

    chunk_size = int(os.getenv("INGEST_CHUNK_SIZE", "2048"))
    chunk_overlap = int(os.getenv("INGEST_CHUNK_OVERLAP", "128"))
    parser = SmartCodeNodeParser(chunk_size=chunk_size, chunk_overlap=chunk_overlap)
    doc = Document(
        text=content,
        metadata={
            "file_path": resolved_fp,
            "file_name": p.name,
            "_tree": tree,
            "_source_bytes": source_bytes,
            "_ast_info": ast_info,
        },
    )
    nodes = parser.get_nodes_from_documents([doc])

    if not nodes:
        cache.record_file(resolved_fp, collection, mtime, sha, [])
        return {
            "status": "indexed",
            "file_path": resolved_fp,
            "chunks": 0,
            "symbols": symbol_count,
            "points": [],
            "cached": 0,
            "misses": 0,
            "changed": True,
        }

    # 6. Embeddings with ChunkEmbeddingCache
    embed_model_name = os.getenv("EMBED_MODEL_NAME", "mlx-community--Qwen3-Embedding-8B-4bit-DWQ")
    texts = [n.get_content() for n in nodes]
    cached_hits, misses = chunk_cache.get_batch(texts, embed_model_name)
    for idx, vec in cached_hits.items():
        nodes[idx].embedding = vec

    if misses:
        batch_size = int(os.getenv("EMBED_BATCH_SIZE", "8"))
        concurrency = int(os.getenv("EMBED_CONCURRENCY", "1"))
        miss_batches = [misses[i:i + batch_size] for i in range(0, len(misses), batch_size)]
        sem = asyncio.Semaphore(concurrency)

        try:
            limits = httpx.Limits(max_keepalive_connections=16, max_connections=32)
            timeout = httpx.Timeout(60.0, connect=10.0, read=60.0)
            async with httpx.AsyncClient(timeout=timeout, limits=limits) as http_client:
                async def embed_batch(batch_idx: int, miss_batch):
                    async with sem:
                        texts = [item[1] for item in miss_batch]
                        for attempt in range(3):
                            try:
                                resp = await http_client.post(
                                    f"{EMBED_BASE_URL}/embeddings",
                                    json={"model": embed_model_name, "input": texts},
                                )
                                resp.raise_for_status()
                                data = resp.json()["data"]
                                new_cache_items = []
                                for (orig_idx, miss_text), item in zip(miss_batch, data):
                                    emb = item["embedding"]
                                    nodes[orig_idx].embedding = emb
                                    new_cache_items.append((miss_text, emb))
                                chunk_cache.put_batch(new_cache_items, embed_model_name)
                                break
                            except Exception as exc:
                                if attempt == 2:
                                    raise
                                await asyncio.sleep(0.5 * (attempt + 1))

                await asyncio.gather(*[embed_batch(i, b) for i, b in enumerate(miss_batches)])
        except Exception as exc:
            logger.error(f"[Kortext Ingest] ⚠️  Embedding failed for {p.name}: {exc}")
            return {
                "status": "error",
                "error": f"Embedding failed: {exc}",
                "file_path": resolved_fp,
                "chunks": 0,
                "symbols": symbol_count,
                "points": [],
                "cached": len(cached_hits),
                "misses": len(misses),
                "changed": True,
            }

    # 7. Upsert valid vectors into Qdrant
    valid_nodes = [n for n in nodes if n.embedding]
    points = []
    point_ids = []

    # Compute sparse BM25 vectors matching batch indexing "text-sparse-new"
    sparse_vectors: Dict[str, qmodels.SparseVector] = {}
    try:
        active_sparse_model = sparse_model or get_sparse_model()
        if active_sparse_model is not None and valid_nodes:
            sparse_texts = [n.get_content() for n in valid_nodes]
            raw_sparse = list(active_sparse_model.embed(sparse_texts))
            for n, semb in zip(valid_nodes, raw_sparse):
                if hasattr(semb, "indices") and hasattr(semb, "values"):
                    s_indices = [int(i) for i in semb.indices]
                    s_values = [float(v) for v in semb.values]
                elif isinstance(semb, dict):
                    s_indices = [int(i) for i in semb.get("indices", [])]
                    s_values = [float(v) for v in semb.get("values", [])]
                elif isinstance(semb, (tuple, list)) and len(semb) == 2:
                    s_indices = [int(i) for i in semb[0]]
                    s_values = [float(v) for v in semb[1]]
                else:
                    s_indices, s_values = [], []

                if s_indices and s_values:
                    sparse_vectors[n.node_id] = qmodels.SparseVector(
                        indices=s_indices,
                        values=s_values,
                    )
    except Exception as exc:
        logger.warning(f"[Kortext Ingest] Diagnostic note generating sparse vectors for {p.name}: {exc}")

    for n in valid_nodes:
        point_ids.append(n.node_id)
        vec_payload: Dict[str, Any] = {"text-dense": n.embedding}
        if n.node_id in sparse_vectors:
            vec_payload["text-sparse-new"] = sparse_vectors[n.node_id]

        points.append(
            qmodels.PointStruct(
                id=n.node_id,
                vector=vec_payload,
                payload={
                    "text": n.get_content(),
                    "file_path": resolved_fp,
                    "file_name": p.name,
                    **n.metadata,
                },
            )
        )

    if points:
        await client.upsert(collection_name=collection, points=points)

    # 8. Record in IngestCache
    cache.record_file(resolved_fp, collection, mtime, sha, point_ids)

    return {
        "status": "indexed",
        "file_path": resolved_fp,
        "chunks": len(points),
        "symbols": symbol_count,
        "points": point_ids,
        "cached": len(cached_hits),
        "misses": len(misses),
        "changed": True,
    }



async def ingest(
    root: str,
    extra_excludes: Optional[List[str]] = None,
    collection: str = COLLECTION,
    force: bool = False,
    symbols_graph: Optional[str] = None,
):
    exclude = DEFAULT_EXCLUDE + (extra_excludes or [])
    target_symbols_db = symbols_graph or (
        f"{collection}_symbols" if collection not in ("kortext_codebase", "cerebrum_codebase") else DEFAULT_SYMBOLS_GRAPH
    )
    logger.info(f"[Kortext Ingest] Indexing: {root}")
    logger.info(f"[Kortext Ingest] Qdrant Collection: {collection} | FalkorDB Symbol Graph: {target_symbols_db} (force={force})")

    embed_model_name = os.getenv("EMBED_MODEL_NAME", "mlx-community--Qwen3-Embedding-8B-4bit-DWQ")
    embed_api_key = os.getenv("EMBED_API_KEY") or os.getenv("OPENAI_API_KEY") or "not-needed"
    embed_model = OpenAIEmbedding(
        api_base=EMBED_BASE_URL,
        api_key=embed_api_key,
        model_name=embed_model_name,
        timeout=300.0,
        max_retries=3,
    )
    Settings.embed_model = embed_model

    client = AsyncQdrantClient(url=QDRANT_URL)
    sync_client = QdrantClient(url=QDRANT_URL)
    cache = IngestCache()

    # Ensure collection exists with hybrid dense + sparse support
    collections = await client.get_collections()
    existing = [c.name for c in collections.collections]

    needs_recreate = False
    if collection in existing:
        col_info = await client.get_collection(collection_name=collection)
        has_sparse = (
            col_info.config.params.sparse_vectors is not None
            and "text-sparse-new" in col_info.config.params.sparse_vectors
        )
        if not has_sparse:
            logger.info(f"[Kortext Ingest] Upgrading collection '{collection}' to hybrid dense + sparse (BM25)...")
            await client.delete_collection(collection)
            cache.clear_collection(collection)
            needs_recreate = True

    embed_dim = int(os.getenv("EMBED_DIMENSION", "4096"))
    if collection not in existing and not needs_recreate:
        if collection in ("kortext_codebase", "kortext") and "cerebrum_codebase" in existing:
            collection = "cerebrum_codebase"
        elif collection in ("cerebrum_codebase", "cerebrum") and "kortext_codebase" in existing:
            collection = "kortext_codebase"

    if collection not in existing or needs_recreate:
        await client.create_collection(
            collection_name=collection,
            vectors_config={"text-dense": qmodels.VectorParams(size=embed_dim, distance=qmodels.Distance.COSINE)},
            sparse_vectors_config={"text-sparse-new": qmodels.SparseVectorParams()},
        )
        logger.info(f"[Kortext Ingest] Created hybrid collection '{collection}' (dense + sparse BM25)")
    else:
        logger.info(f"[Kortext Ingest] Using existing hybrid collection '{collection}' (upsert mode)")

    store = QdrantVectorStore(
        client=sync_client,
        collection_name=collection,
        aclient=client,
        enable_hybrid=True,
        fastembed_sparse_model="Qdrant/bm25",
    )

    try:
        reader = SimpleDirectoryReader(
            input_dir=root,
            recursive=True,
            required_exts=list(SUPPORTED_EXT),
            exclude=exclude,
        )
        docs = reader.load_data()
    except Exception as e:
        logger.error(f"[Kortext Ingest] Error reading directory: {e}")
        return

    if not docs:
        logger.warning("[Kortext Ingest] ⚠️  No matching documents found.")
        return

    # 1. Content-Hash Incremental Ingestion Check
    current_files = {str(Path(d.metadata["file_path"]).resolve()) for d in docs if "file_path" in d.metadata}

    # Purge deleted files
    purged = cache.purge_missing_files(collection, current_files)
    if purged:
        logger.info(f"[Kortext Ingest] 🗑️  Purging {len(purged)} deleted file(s) from collection '{collection}'...")
        from kortext.symbols import SymbolGraphManager
        symbol_graph = SymbolGraphManager(graph_name=target_symbols_db)
        for purged_file, old_points in purged:
            if old_points:
                try:
                    await client.delete(
                        collection_name=collection,
                        points_selector=qmodels.PointIdsList(points=old_points),
                    )
                except Exception as exc:
                    logger.warning(f"[Kortext Ingest] Warning: Failed to delete points for {purged_file}: {exc}")
            try:
                symbol_graph.delete_file_ast(purged_file)
            except Exception as exc:
                logger.warning(f"[Kortext Ingest] Warning: Failed to delete symbol AST for {purged_file}: {exc}")

    docs_to_index = []
    files_to_reindex = {}  # {resolved_fp: (mtime, sha, old_points)}

    for doc in docs:
        fp = doc.metadata.get("file_path")
        if not fp:
            docs_to_index.append(doc)
            continue
        p = Path(fp).resolve()
        resolved_fp = str(p)

        # Guardrail: Check file size ceiling
        try:
            st = p.stat()
            if st.st_size > MAX_FILE_SIZE_BYTES:
                logger.warning(f"[Kortext Ingest] ⚠️  Skipping large file {p.name} ({st.st_size} bytes > {MAX_FILE_SIZE_BYTES})")
                continue
        except Exception:
            pass

        # Guardrail: Binary detection
        try:
            with open(p, "rb") as bf:
                header = bf.read(8192)
                if b"\x00" in header:
                    logger.debug(f"[Kortext Ingest] Skipping binary file: {p.name}")
                    continue
        except Exception as exc:
            pass

        if force:
            changed = True
            mtime, sha = IngestCache.get_file_stats(Path(resolved_fp))
            old_points = cache.get_all_cached_files(collection).get(resolved_fp, [])
        else:
            changed, mtime, sha, old_points = cache.is_file_changed(resolved_fp, collection)

        if changed:
            docs_to_index.append(doc)
            files_to_reindex[resolved_fp] = (mtime, sha, old_points)

    if not docs_to_index:
        logger.info(f"[Kortext Ingest] ⚡ All {len(docs)} files are up-to-date in cache. Nothing to index.")
        return

    logger.info(f"[Kortext Ingest] Detected {len(docs_to_index)} modified or new file(s) out of {len(docs)} total files.")

    # Delete stale vector points for modified files before upserting new ones
    for resolved_fp, (_, _, old_points) in files_to_reindex.items():
        if old_points:
            try:
                await client.delete(
                    collection_name=collection,
                    points_selector=qmodels.PointIdsList(points=old_points),
                )
            except Exception:
                pass

    # 2. Auto-detect and ingest compiler-grade SCIP index if present in workspace root
    scip_candidates = [
        Path(root) / "index.scip",
        Path(root) / ".scip",
        Path(root) / "dump.scip",
    ]
    scip_ingested = False
    for scip_path in scip_candidates:
        if scip_path.is_file():
            try:
                from kortext.symbols.scip import SCIPImporter
                scip_imp = SCIPImporter(graph_name=target_symbols_db)
                scip_res = scip_imp.ingest_index(scip_path, purge_existing=False)
                logger.info(
                    f"[Kortext Ingest] Auto-ingested compiler-grade SCIP index ({scip_path.name}): "
                    f"{scip_res['symbols_indexed']} symbols, {scip_res['references_indexed']} references, "
                    f"{scip_res['relationships_indexed']} type relationships."
                )
                scip_ingested = True
                break
            except Exception as e:
                logger.warning(f"[Kortext Ingest] Warning auto-ingesting SCIP index {scip_path}: {e}")

    # If no SCIP index file found, check if project manifest exists and auto-indexing is viable
    if not scip_ingested:
        try:
            from kortext.symbols.scip import detect_project_scip_indexer, auto_index_and_ingest
            detector = detect_project_scip_indexer(root)
            if detector.get("binary"):
                auto_res = auto_index_and_ingest(root, graph_name=target_symbols_db, purge_existing=False)
                if auto_res.get("status") == "missing_indexer":
                    logger.info(
                        f"[Kortext Ingest] Compiler manifest detected ({detector['manifest']}) for language '{detector['language']}'. "
                        f"Install '{detector['install_hint']}' to upgrade to 100% type-checked semantic graphs. "
                        f"Using Tree-sitter AST fallback."
                    )
                elif auto_res.get("documents_indexed", 0) > 0:
                    logger.info(
                        f"[Kortext Ingest] Compiler-grade SCIP index generated & ingested: "
                        f"{auto_res['symbols_indexed']} symbols, {auto_res['references_indexed']} references, "
                        f"{auto_res['relationships_indexed']} type relationships."
                    )
        except Exception as e:
            logger.warning(f"[Kortext Ingest] Diagnostic note checking compiler SCIP indexer: {e}")

    # 3. Chunked Streaming Ingestion for bounded RAM usage
    from kortext.symbols import SymbolGraphManager, MarkdownSymbolExtractor
    from kortext.chunking.ast_splitter import LANG_MAP, ASTCodeSplitter
    from kortext.chunking import SmartCodeNodeParser

    symbol_graph = SymbolGraphManager(graph_name=target_symbols_db)
    md_extractor = MarkdownSymbolExtractor(workspace_root=root)

    chunk_size = int(os.getenv("INGEST_CHUNK_SIZE", "2048"))
    chunk_overlap = int(os.getenv("INGEST_CHUNK_OVERLAP", "128"))
    parser = SmartCodeNodeParser(chunk_size=chunk_size, chunk_overlap=chunk_overlap)

    chunk_cache = ChunkEmbeddingCache()
    batch_size = int(os.getenv("EMBED_BATCH_SIZE", "8"))
    concurrency = int(os.getenv("EMBED_CONCURRENCY", "1"))
    BATCH_DOC_COUNT = int(os.getenv("INGEST_BATCH_DOC_COUNT", "50"))

    total_indexed_chunks = 0
    total_decls = 0
    total_refs = 0
    total_docs = 0
    total_doc_links = 0
    total_batches = (len(docs_to_index) + BATCH_DOC_COUNT - 1) // BATCH_DOC_COUNT

    for batch_idx, batch_start in enumerate(range(0, len(docs_to_index), BATCH_DOC_COUNT)):
        batch_docs = docs_to_index[batch_start : batch_start + BATCH_DOC_COUNT]
        current_batch_num = batch_idx + 1

        # 1. AST symbol / Markdown extraction for this batch of documents
        for doc in batch_docs:
            fp = doc.metadata.get("file_path", "")
            ext = Path(fp).suffix.lower() if fp else ""
            if ext in LANG_MAP:
                try:
                    splitter = ASTCodeSplitter(language=LANG_MAP[ext])
                    source_bytes = doc.text.encode("utf-8")
                    tree = splitter.parser.parse(source_bytes) if hasattr(splitter, "parser") else None
                    res = splitter.extract_symbols_and_references(
                        doc.text, file_path=fp, tree=tree, source_bytes=source_bytes
                    )
                    symbol_graph.save_file_ast(fp, res["declarations"], res["imports"], res["references"])
                    total_decls += len(res["declarations"])
                    total_refs += len(res["references"])
                    doc.metadata["_tree"] = tree
                    doc.metadata["_source_bytes"] = source_bytes
                    doc.metadata["_ast_info"] = res
                except Exception as e:
                    logger.warning(f"[Kortext Ingest] Warning extracting symbols for {fp}: {e}")
            elif ext in (".md", ".markdown"):
                try:
                    md_res = md_extractor.extract(doc.text, file_path=fp)
                    symbol_graph.save_markdown_ast(
                        file_path=md_res["file_path"],
                        title=md_res["title"],
                        frontmatter=md_res["frontmatter"],
                        sections=md_res["sections"],
                        declarations=md_res["declarations"],
                        links=md_res["links"],
                        tags=md_res["tags"],
                    )
                    total_docs += 1
                    total_decls += len(md_res["declarations"])
                    total_doc_links += len(md_res["links"])
                except Exception as e:
                    logger.warning(f"[Kortext Ingest] Warning extracting markdown structure for {fp}: {e}")

        # 2. Chunk nodes for this batch
        nodes = parser.get_nodes_from_documents(batch_docs, show_progress=False)

        if not nodes:
            for doc in batch_docs:
                fp = doc.metadata.get("file_path")
                if fp:
                    resolved_fp = str(Path(fp).resolve())
                    if resolved_fp in files_to_reindex:
                        mtime, sha, _ = files_to_reindex[resolved_fp]
                        cache.record_file(resolved_fp, collection, mtime, sha, [])
            logger.info(
                f"[Kortext Ingest] Processed batch {current_batch_num}/{total_batches} "
                f"({len(batch_docs)} files, 0 chunks)"
            )
            continue

        # 3. Lookup ChunkEmbeddingCache and embed misses in batches of EMBED_BATCH_SIZE (8)
        all_texts = [n.get_content() for n in nodes]
        cached_hits, cache_misses = chunk_cache.get_batch(all_texts, embed_model_name)

        # Assign cached embeddings immediately
        for orig_idx, vec in cached_hits.items():
            nodes[orig_idx].embedding = vec

        if cache_misses:
            miss_batches = [cache_misses[i : i + batch_size] for i in range(0, len(cache_misses), batch_size)]
            total_miss_batches = len(miss_batches)

            sem = asyncio.Semaphore(concurrency)
            completed_batches = 0

            limits = httpx.Limits(max_keepalive_connections=32, max_connections=64)
            timeout = httpx.Timeout(600.0, connect=30.0, read=600.0)
            async with httpx.AsyncClient(timeout=timeout, limits=limits) as http_client:
                async def embed_batch(b_idx: int, miss_batch):
                    nonlocal completed_batches
                    async with sem:
                        texts = [item[1] for item in miss_batch]
                        for attempt in range(3):
                            try:
                                resp = await http_client.post(
                                    f"{EMBED_BASE_URL}/embeddings",
                                    json={"model": embed_model_name, "input": texts},
                                )
                                resp.raise_for_status()
                                data = resp.json()["data"]
                                new_cache_items = []
                                for (orig_idx, miss_text), item in zip(miss_batch, data):
                                    emb = item["embedding"]
                                    nodes[orig_idx].embedding = emb
                                    new_cache_items.append((miss_text, emb))
                                chunk_cache.put_batch(new_cache_items, embed_model_name)
                                break
                            except Exception as exc:
                                err_name = f"{type(exc).__name__}: {exc or 'timeout'}"
                                if attempt == 2:
                                    logger.error(
                                        f"[Kortext Ingest] ⚠️  Batch {b_idx + 1}/{total_miss_batches} "
                                        f"failed after 3 retries ({err_name}). Skipping batch."
                                    )
                                else:
                                    await asyncio.sleep(2.0 * (attempt + 1))

                        completed_batches += 1

                await asyncio.gather(*[embed_batch(i, b) for i, b in enumerate(miss_batches)])

        # 4. Write valid nodes for this batch into Qdrant via storage_context / VectorStoreIndex
        valid_nodes = [n for n in nodes if n.embedding is not None]
        if valid_nodes:
            storage_context = StorageContext.from_defaults(vector_store=store)
            VectorStoreIndex(
                nodes=valid_nodes,
                storage_context=storage_context,
                embed_model=embed_model,
                show_progress=False,
            )
            total_indexed_chunks += len(valid_nodes)

        # 5. Record file cache in IngestCache for this batch
        batch_file_to_nodes: Dict[str, List[str]] = {}
        for n in valid_nodes:
            fp = n.metadata.get("file_path")
            if fp:
                batch_file_to_nodes.setdefault(str(Path(fp).resolve()), []).append(n.node_id)

        for doc in batch_docs:
            fp = doc.metadata.get("file_path")
            if fp:
                resolved_fp = str(Path(fp).resolve())
                if resolved_fp in files_to_reindex:
                    mtime, sha, _ = files_to_reindex[resolved_fp]
                    node_ids = batch_file_to_nodes.get(resolved_fp, [])
                    cache.record_file(resolved_fp, collection, mtime, sha, node_ids)

        # Log progress
        logger.info(
            f"[Kortext Ingest] Processed batch {current_batch_num}/{total_batches} "
            f"({len(batch_docs)} files, {len(valid_nodes)} chunks)"
        )

    if total_decls > 0 or total_doc_links > 0 or total_docs > 0:
        msg_parts = []
        if total_decls > 0:
            msg_parts.append(f"{total_decls} symbols/sections")
        if total_refs > 0:
            msg_parts.append(f"{total_refs} code references")
        if total_docs > 0:
            msg_parts.append(f"{total_docs} markdown notes ({total_doc_links} links)")
        logger.info(f"[Kortext Ingest] 🌐 Indexed {', '.join(msg_parts)} in FalkorDB ({target_symbols_db}).")

    logger.info(f"[Kortext Ingest] Done: {total_indexed_chunks} chunks from {len(docs_to_index)} modified files indexed into '{collection}'")


index_workspace = ingest


def main():
    parser = argparse.ArgumentParser(description="Kortext workspace ingestor")
    parser.add_argument("--root", required=True, help="Directory to index")
    parser.add_argument("--collection", default=COLLECTION, help="Qdrant collection name")
    parser.add_argument("--symbols-graph", default=None, help="FalkorDB symbol graph name (defaults to <collection>_symbols)")
    parser.add_argument("--exclude", nargs="*", default=[], help="Extra exclusion patterns")
    parser.add_argument("--force", action="store_true", help="Force re-index all files ignoring cache")
    args = parser.parse_args()

    if not Path(args.root).exists():
        logger.error(f"[Kortext Ingest] Error: {args.root} does not exist")
        sys.exit(1)

    asyncio.run(ingest(args.root, extra_excludes=args.exclude, collection=args.collection, force=args.force, symbols_graph=args.symbols_graph))


if __name__ == "__main__":
    main()
