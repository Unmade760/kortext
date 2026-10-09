"""
Centralized Zero-Config Dense Embedding Provider with FastEmbed Fallback.

Provides a unified DenseEmbedder interface with:
1. FastEmbedDenseProvider: Local ONNX-based dense vector generation via fastembed
   (default 'BAAI/bge-small-en-v1.5', dimension 384). Cached as a memory singleton.
2. RemoteDenseProvider: Remote MLX/OpenAI-compatible embedding server over HTTP
   (default 'mlx-community--Qwen3-Embedding-8B-4bit-DWQ', dimension 4096)
   with retry and timeout management.
3. get_dense_embedder: Zero-config factory with automatic health probe and graceful fallback.
"""

from __future__ import annotations

import asyncio
import logging
import os
import time
from dataclasses import dataclass
from typing import Any, Dict, List, Optional, Protocol, Tuple, runtime_checkable

import httpx

from kortext._env import get_embed_base_url, get_embed_model_name

logger = logging.getLogger("kortext.embeddings")

__all__ = [
    "DenseEmbedder",
    "DenseEmbedderProtocol",
    "EmbeddingConfig",
    "EmbeddingError",
    "RemoteEmbeddingError",
    "FastEmbedError",
    "FastEmbedDenseProvider",
    "RemoteDenseProvider",
    "is_remote_embed_alive",
    "get_dense_embedder",
]

# Global model cache to avoid re-initializing ONNX sessions across provider instances
_FASTEMBED_MODEL_CACHE: Dict[Tuple[str, Optional[str]], Any] = {}
# Global singleton cache for FastEmbedDenseProvider instances
_FASTEMBED_PROVIDER_CACHE: Dict[str, FastEmbedDenseProvider] = {}


class EmbeddingError(Exception):
    """Base exception for all embedding provider errors."""


class RemoteEmbeddingError(EmbeddingError):
    """Raised when remote embedding service fails or exhausts retries."""


class FastEmbedError(EmbeddingError):
    """Raised when local FastEmbed embedding encounters an error."""


@dataclass(frozen=True)
class EmbeddingConfig:
    """Immutable configuration for dense embedding providers."""

    base_url: Optional[str] = None
    remote_model_name: str = "mlx-community--Qwen3-Embedding-8B-4bit-DWQ"
    fastembed_model_name: str = "BAAI/bge-small-en-v1.5"
    remote_dimension: int = 4096
    fastembed_dimension: int = 384
    timeout: float = 30.0
    probe_timeout: float = 1.0
    max_retries: int = 3
    api_key: Optional[str] = None


@runtime_checkable
class DenseEmbedder(Protocol):
    """Protocol defining the interface for dense embedding providers."""

    @property
    def dimension(self) -> int:
        """Vector dimensionality of the embedding model."""
        ...

    def embed_documents(self, documents: List[str]) -> List[List[float]]:
        """Compute dense vector embeddings for a batch of documents."""
        ...

    def embed_query(self, query: str) -> List[float]:
        """Compute a dense vector embedding for a single query."""
        ...


DenseEmbedderProtocol = DenseEmbedder


class FastEmbedDenseProvider:
    """
    Local zero-config embedding provider powered by fastembed.TextEmbedding.
    Uses singleton caching to avoid reload overhead.
    """

    def __init__(
        self,
        model_name: str = "BAAI/bge-small-en-v1.5",
        cache_dir: Optional[str] = None,
        threads: Optional[int] = None,
    ) -> None:
        self._model_name = model_name
        self._cache_dir = cache_dir
        self._threads = threads

        # Resolve dimension deterministically
        if "bge-small" in model_name:
            self._dimension = 384
        else:
            try:
                from fastembed import TextEmbedding

                self._dimension = TextEmbedding.get_embedding_size(model_name)
            except Exception:
                self._dimension = 384

    @property
    def model_name(self) -> str:
        """Name of the FastEmbed model."""
        return self._model_name

    @property
    def dimension(self) -> int:
        """Dimension of generated dense embeddings."""
        return self._dimension

    @property
    def model(self) -> Any:
        """Returns the cached singleton TextEmbedding model instance."""
        cache_key = (self._model_name, self._cache_dir)
        if cache_key not in _FASTEMBED_MODEL_CACHE:
            try:
                from fastembed import TextEmbedding

                init_kwargs: Dict[str, Any] = {"model_name": self._model_name}
                if self._cache_dir is not None:
                    init_kwargs["cache_dir"] = self._cache_dir
                if self._threads is not None:
                    init_kwargs["threads"] = self._threads

                logger.info("Initializing FastEmbed TextEmbedding singleton for %s", self._model_name)
                _FASTEMBED_MODEL_CACHE[cache_key] = TextEmbedding(**init_kwargs)
            except Exception as exc:
                logger.error("Failed to initialize FastEmbed model %s: %s", self._model_name, exc)
                raise FastEmbedError(f"Failed to initialize FastEmbed model '{self._model_name}': {exc}") from exc

        return _FASTEMBED_MODEL_CACHE[cache_key]

    def embed_documents(self, documents: List[str]) -> List[List[float]]:
        """Compute dense vector embeddings for a batch of documents."""
        if not documents:
            return []

        try:
            embeddings_iter = self.model.embed(documents)
            results: List[List[float]] = []
            for item in embeddings_iter:
                if hasattr(item, "tolist"):
                    results.append([float(x) for x in item.tolist()])
                else:
                    results.append([float(x) for x in item])
            return results
        except Exception as exc:
            logger.error("FastEmbed batch embedding failed: %s", exc)
            raise FastEmbedError(f"FastEmbed embedding error: {exc}") from exc

    def embed_query(self, query: str) -> List[float]:
        """Compute a dense vector embedding for a single query."""
        try:
            results_iter = self.model.query_embed(query)
            for item in results_iter:
                if hasattr(item, "tolist"):
                    return [float(x) for x in item.tolist()]
                return [float(x) for x in item]
            return [0.0] * self._dimension
        except Exception as exc:
            logger.error("FastEmbed query embedding failed: %s", exc)
            raise FastEmbedError(f"FastEmbed query embedding error: {exc}") from exc

    async def aembed_documents(self, documents: List[str]) -> List[List[float]]:
        """Asynchronously compute embeddings for documents via thread pool."""
        return await asyncio.to_thread(self.embed_documents, documents)

    async def aembed_query(self, query: str) -> List[float]:
        """Asynchronously compute embedding for query via thread pool."""
        return await asyncio.to_thread(self.embed_query, query)


class RemoteDenseProvider:
    """
    HTTP client targeting an OpenAI-compatible /embeddings endpoint (e.g. oMLX / Qwen3).
    Includes timeouts, exponential backoff retries, and strict error handling.
    """

    def __init__(
        self,
        base_url: Optional[str] = None,
        model_name: Optional[str] = None,
        dimension: Optional[int] = None,
        timeout: float = 30.0,
        max_retries: int = 3,
        api_key: Optional[str] = None,
    ) -> None:
        raw_url = (base_url or get_embed_base_url()).rstrip("/")
        self._base_url = raw_url.replace("://localhost", "://127.0.0.1")
        self._model_name = model_name or get_embed_model_name()
        self._timeout = timeout
        self._max_retries = max(1, max_retries)
        self._api_key = api_key or os.getenv("EMBED_API_KEY") or os.getenv("OPENAI_API_KEY")

        if dimension is not None:
            self._dimension = dimension
        elif any(sig in self._model_name for sig in ("mlx", "Qwen3", "8B")):
            self._dimension = 4096
        else:
            self._dimension = 4096

    @property
    def base_url(self) -> str:
        """Target base URL for the embedding server."""
        return self._base_url

    @property
    def model_name(self) -> str:
        """Model identifier sent in payload."""
        return self._model_name

    @property
    def dimension(self) -> int:
        """Dimension of generated dense embeddings."""
        return self._dimension

    def _get_headers(self) -> Dict[str, str]:
        headers = {"Content-Type": "application/json"}
        if self._api_key:
            headers["Authorization"] = f"Bearer {self._api_key}"
        return headers

    def embed_documents(self, documents: List[str]) -> List[List[float]]:
        """Compute dense vector embeddings for a batch of documents with retries."""
        if not documents:
            return []

        payload = {
            "model": self._model_name,
            "input": documents,
        }
        url = f"{self._base_url}/embeddings"
        headers = self._get_headers()

        last_error: Optional[Exception] = None

        for attempt in range(1, self._max_retries + 1):
            try:
                with httpx.Client(timeout=self._timeout) as client:
                    resp = client.post(url, json=payload, headers=headers)
                    resp.raise_for_status()
                    data = resp.json()

                    raw_items = data.get("data", [])
                    sorted_items = sorted(raw_items, key=lambda x: x.get("index", 0))
                    embeddings: List[List[float]] = []
                    for item in sorted_items:
                        vec = item.get("embedding", [])
                        embeddings.append([float(x) for x in vec])
                    return embeddings

            except (httpx.RequestError, httpx.HTTPStatusError) as exc:
                last_error = exc
                status = getattr(getattr(exc, "response", None), "status_code", None)
                # Retry on transport errors or 5xx server errors
                is_retryable = isinstance(exc, httpx.RequestError) or (status is not None and status >= 500)
                if is_retryable and attempt < self._max_retries:
                    sleep_time = min(0.1 * (2 ** (attempt - 1)), 2.0)
                    logger.warning(
                        "Remote embedding attempt %d/%d failed with %s. Retrying in %.2fs...",
                        attempt,
                        self._max_retries,
                        exc,
                        sleep_time,
                    )
                    time.sleep(sleep_time)
                    continue

                logger.error("Remote embedding request failed (attempt %d/%d): %s", attempt, self._max_retries, exc)
                raise RemoteEmbeddingError(f"Remote embedding failed at {url}: {exc}") from exc

            except Exception as exc:
                logger.error("Unexpected error in remote embedding request: %s", exc)
                raise RemoteEmbeddingError(f"Unexpected remote embedding failure: {exc}") from exc

        raise RemoteEmbeddingError(f"Exhausted {self._max_retries} attempts for remote embedding: {last_error}")

    def embed_query(self, query: str) -> List[float]:
        """Compute a dense vector embedding for a single query."""
        results = self.embed_documents([query])
        if not results:
            return [0.0] * self._dimension
        return results[0]

    async def aembed_documents(self, documents: List[str]) -> List[List[float]]:
        """Asynchronously compute embeddings with AsyncClient."""
        if not documents:
            return []

        payload = {
            "model": self._model_name,
            "input": documents,
        }
        url = f"{self._base_url}/embeddings"
        headers = self._get_headers()

        last_error: Optional[Exception] = None

        for attempt in range(1, self._max_retries + 1):
            try:
                async with httpx.AsyncClient(timeout=self._timeout) as client:
                    resp = await client.post(url, json=payload, headers=headers)
                    resp.raise_for_status()
                    data = resp.json()

                    raw_items = data.get("data", [])
                    sorted_items = sorted(raw_items, key=lambda x: x.get("index", 0))
                    embeddings: List[List[float]] = []
                    for item in sorted_items:
                        vec = item.get("embedding", [])
                        embeddings.append([float(x) for x in vec])
                    return embeddings

            except (httpx.RequestError, httpx.HTTPStatusError) as exc:
                last_error = exc
                status = getattr(getattr(exc, "response", None), "status_code", None)
                is_retryable = isinstance(exc, httpx.RequestError) or (status is not None and status >= 500)
                if is_retryable and attempt < self._max_retries:
                    sleep_time = min(0.1 * (2 ** (attempt - 1)), 2.0)
                    await asyncio.sleep(sleep_time)
                    continue

                raise RemoteEmbeddingError(f"Remote embedding failed at {url}: {exc}") from exc

            except Exception as exc:
                raise RemoteEmbeddingError(f"Unexpected remote embedding failure: {exc}") from exc

        raise RemoteEmbeddingError(f"Exhausted {self._max_retries} attempts for remote embedding: {last_error}")

    async def aembed_query(self, query: str) -> List[float]:
        """Asynchronously compute embedding for query."""
        results = await self.aembed_documents([query])
        if not results:
            return [0.0] * self._dimension
        return results[0]


def is_remote_embed_alive(base_url: Optional[str] = None, timeout: float = 1.0) -> bool:
    """
    Performs a lightweight GET/HEAD probe to check if the remote embedding server is alive.
    Returns False if offline, connection refused, or unset.
    """
    if base_url is not None:
        target_url = base_url.strip()
    else:
        from kortext._env import get_env

        env_url = get_env("EMBED_BASE_URL")
        if not env_url:
            return False
        target_url = env_url.strip()

    if not target_url or target_url.lower() in ("none", "disabled", "false", "0"):
        return False

    if not target_url.startswith(("http://", "https://")):
        target_url = f"http://{target_url}"

    probe_url = target_url.rstrip("/").replace("://localhost", "://127.0.0.1")

    try:
        with httpx.Client(timeout=timeout) as client:
            # 1. Try standard OpenAI /models endpoint
            try:
                resp = client.get(f"{probe_url}/models")
                if resp.status_code < 500:
                    return True
            except (httpx.ConnectError, httpx.ConnectTimeout):
                return False
            except httpx.HTTPError:
                pass

            # 2. Fallback probe to root base URL
            try:
                resp = client.get(probe_url)
                return resp.status_code < 500
            except (httpx.ConnectError, httpx.ConnectTimeout):
                return False
            except httpx.HTTPError:
                resp = client.head(probe_url)
                return resp.status_code < 500

    except Exception:
        return False


def get_dense_embedder(
    force_fastembed: bool = False,
    model_name: Optional[str] = None,
    base_url: Optional[str] = None,
) -> DenseEmbedder:
    """
    Zero-config dense embedder factory with automatic FastEmbed fallback.

    1. If `force_fastembed` is True, returns singleton FastEmbedDenseProvider.
    2. Checks if remote `EMBED_BASE_URL` is alive via lightweight probe.
    3. If online, returns RemoteDenseProvider.
    4. If offline, unreachable, or connection refused, logs and falls back to
       singleton FastEmbedDenseProvider.
    """
    if not force_fastembed and is_remote_embed_alive(base_url=base_url):
        logger.info("Connecting to online remote embedding provider (%s)", model_name or get_embed_model_name())
        return RemoteDenseProvider(base_url=base_url, model_name=model_name)

    # Fallback to local FastEmbed singleton
    target_model = model_name or "BAAI/bge-small-en-v1.5"
    if target_model not in _FASTEMBED_PROVIDER_CACHE:
        logger.info(
            "Remote embedding provider unreachable or forced; initializing local FastEmbed provider (%s)",
            target_model,
        )
        _FASTEMBED_PROVIDER_CACHE[target_model] = FastEmbedDenseProvider(model_name=target_model)

    return _FASTEMBED_PROVIDER_CACHE[target_model]
