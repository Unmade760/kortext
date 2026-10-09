"""
Unit tests for centralized environment variable resolver in kortext._env.
"""

from pathlib import Path
from unittest.mock import patch
import pytest

from kortext._env import (
    get_env,
    get_int_env,
    get_float_env,
    get_bool_env,
    get_falkordb_socket,
    get_falkordb_host,
    get_falkordb_port,
    get_falkordb_database,
    get_falkordb_symbols_graph,
    get_qdrant_url,
    get_qdrant_collection,
    get_embed_base_url,
    get_embed_model_name,
    get_rerank_base_url,
)
import kortext


def test_kortext_package_exports():
    expected_exports = [
        "get_env",
        "get_int_env",
        "get_float_env",
        "get_bool_env",
        "get_falkordb_socket",
        "get_falkordb_host",
        "get_falkordb_port",
        "get_falkordb_database",
        "get_falkordb_symbols_graph",
        "get_qdrant_url",
        "get_qdrant_collection",
        "get_embed_base_url",
        "get_embed_model_name",
        "get_rerank_base_url",
    ]
    for name in expected_exports:
        assert hasattr(kortext, name), f"kortext is missing export {name}"



class TestGetEnv:
    def test_kortext_prefix_takes_precedence_over_cerebrum_and_raw(self, monkeypatch):
        monkeypatch.setenv("KORTEXT_TEST_VAR", "kortext_val")
        monkeypatch.setenv("CEREBRUM_TEST_VAR", "cerebrum_val")
        monkeypatch.setenv("TEST_VAR", "raw_val")

        assert get_env("TEST_VAR") == "kortext_val"

    def test_fallback_to_cerebrum_when_kortext_is_absent(self, monkeypatch):
        monkeypatch.delenv("KORTEXT_TEST_VAR", raising=False)
        monkeypatch.setenv("CEREBRUM_TEST_VAR", "cerebrum_val")
        monkeypatch.setenv("TEST_VAR", "raw_val")

        assert get_env("TEST_VAR") == "cerebrum_val"

    def test_fallback_to_cerebrum_when_kortext_is_empty(self, monkeypatch):
        monkeypatch.setenv("KORTEXT_TEST_VAR", "")
        monkeypatch.setenv("CEREBRUM_TEST_VAR", "cerebrum_val")
        monkeypatch.setenv("TEST_VAR", "raw_val")

        assert get_env("TEST_VAR") == "cerebrum_val"

    def test_fallback_to_raw_name_when_both_prefixes_absent(self, monkeypatch):
        monkeypatch.delenv("KORTEXT_TEST_VAR", raising=False)
        monkeypatch.delenv("CEREBRUM_TEST_VAR", raising=False)
        monkeypatch.setenv("TEST_VAR", "raw_val")

        assert get_env("TEST_VAR") == "raw_val"

    def test_fallback_to_raw_name_when_both_prefixes_empty(self, monkeypatch):
        monkeypatch.setenv("KORTEXT_TEST_VAR", "")
        monkeypatch.setenv("CEREBRUM_TEST_VAR", "")
        monkeypatch.setenv("TEST_VAR", "raw_val")

        assert get_env("TEST_VAR") == "raw_val"

    def test_fallback_to_default_when_all_absent_or_empty(self, monkeypatch):
        monkeypatch.delenv("KORTEXT_TEST_VAR", raising=False)
        monkeypatch.delenv("CEREBRUM_TEST_VAR", raising=False)
        monkeypatch.delenv("TEST_VAR", raising=False)

        assert get_env("TEST_VAR", "default_val") == "default_val"
        assert get_env("TEST_VAR") is None

        monkeypatch.setenv("TEST_VAR", "")
        assert get_env("TEST_VAR", "default_val") == "default_val"

    def test_direct_lookup_when_name_starts_with_kortext_prefix(self, monkeypatch):
        monkeypatch.setenv("KORTEXT_CUSTOM_VAR", "explicit_kortext")
        assert get_env("KORTEXT_CUSTOM_VAR") == "explicit_kortext"

    def test_direct_lookup_when_name_starts_with_cerebrum_prefix(self, monkeypatch):
        monkeypatch.setenv("CEREBRUM_CUSTOM_VAR", "explicit_cerebrum")
        assert get_env("CEREBRUM_CUSTOM_VAR") == "explicit_cerebrum"

    def test_direct_lookup_kortext_fallback_to_cerebrum_if_absent(self, monkeypatch):
        monkeypatch.delenv("KORTEXT_LEGACY_KEY", raising=False)
        monkeypatch.setenv("CEREBRUM_LEGACY_KEY", "legacy_val")
        assert get_env("KORTEXT_LEGACY_KEY") == "legacy_val"


class TestTypedGetters:
    def test_get_int_env(self, monkeypatch):
        monkeypatch.setenv("KORTEXT_TEST_INT", "42")
        assert get_int_env("TEST_INT", 10) == 42

        # Fallback to CEREBRUM
        monkeypatch.delenv("KORTEXT_TEST_INT", raising=False)
        monkeypatch.setenv("CEREBRUM_TEST_INT", "84")
        assert get_int_env("TEST_INT", 10) == 84

        # Fallback to raw
        monkeypatch.delenv("CEREBRUM_TEST_INT", raising=False)
        monkeypatch.setenv("TEST_INT", "100")
        assert get_int_env("TEST_INT", 10) == 100

        # Default on missing
        monkeypatch.delenv("TEST_INT", raising=False)
        assert get_int_env("TEST_INT", 10) == 10

        # Default on invalid
        monkeypatch.setenv("TEST_INT", "invalid_int")
        assert get_int_env("TEST_INT", 10) == 10

    def test_get_float_env(self, monkeypatch):
        monkeypatch.setenv("KORTEXT_TEST_FLOAT", "3.1415")
        assert get_float_env("TEST_FLOAT", 1.0) == pytest.approx(3.1415)

        # Fallback to CEREBRUM
        monkeypatch.delenv("KORTEXT_TEST_FLOAT", raising=False)
        monkeypatch.setenv("CEREBRUM_TEST_FLOAT", "2.718")
        assert get_float_env("TEST_FLOAT", 1.0) == pytest.approx(2.718)

        # Fallback to raw
        monkeypatch.delenv("CEREBRUM_TEST_FLOAT", raising=False)
        monkeypatch.setenv("TEST_FLOAT", "0.5")
        assert get_float_env("TEST_FLOAT", 1.0) == pytest.approx(0.5)

        # Default on missing
        monkeypatch.delenv("TEST_FLOAT", raising=False)
        assert get_float_env("TEST_FLOAT", 1.0) == pytest.approx(1.0)

        # Default on invalid
        monkeypatch.setenv("TEST_FLOAT", "invalid_float")
        assert get_float_env("TEST_FLOAT", 1.0) == pytest.approx(1.0)

    @pytest.mark.parametrize(
        "raw_val, expected",
        [
            ("1", True),
            ("true", True),
            ("TRUE", True),
            ("True", True),
            ("yes", True),
            ("YES", True),
            ("y", True),
            ("t", True),
            ("on", True),
            ("0", False),
            ("false", False),
            ("FALSE", False),
            ("False", False),
            ("no", False),
            ("NO", False),
            ("n", False),
            ("f", False),
            ("off", False),
        ],
    )
    def test_get_bool_env_truthy_falsy(self, monkeypatch, raw_val, expected):
        monkeypatch.setenv("KORTEXT_TEST_BOOL", raw_val)
        assert get_bool_env("TEST_BOOL", not expected) is expected

    def test_get_bool_env_default_on_missing_or_invalid(self, monkeypatch):
        monkeypatch.delenv("KORTEXT_TEST_BOOL", raising=False)
        monkeypatch.delenv("CEREBRUM_TEST_BOOL", raising=False)
        monkeypatch.delenv("TEST_BOOL", raising=False)

        assert get_bool_env("TEST_BOOL", True) is True
        assert get_bool_env("TEST_BOOL", False) is False

        monkeypatch.setenv("TEST_BOOL", "not_a_boolean")
        assert get_bool_env("TEST_BOOL", True) is True
        assert get_bool_env("TEST_BOOL", False) is False


class TestSpecializedGetters:
    def test_get_falkordb_socket_default(self, monkeypatch, tmp_path):
        monkeypatch.delenv("KORTEXT_FALKORDB_SOCKET", raising=False)
        monkeypatch.delenv("CEREBRUM_FALKORDB_SOCKET", raising=False)
        monkeypatch.delenv("FALKORDB_SOCKET", raising=False)

        fake_home = tmp_path / "kortext_home"
        monkeypatch.setenv("KORTEXT_HOME", str(fake_home))

        expected = fake_home / "run" / "falkordb.sock"
        assert get_falkordb_socket() == expected

    def test_get_falkordb_socket_override(self, monkeypatch, tmp_path):
        custom_sock = tmp_path / "custom.sock"
        monkeypatch.setenv("FALKORDB_SOCKET", str(custom_sock))
        assert get_falkordb_socket() == custom_sock

        monkeypatch.setenv("CEREBRUM_FALKORDB_SOCKET", str(tmp_path / "cerebrum.sock"))
        assert get_falkordb_socket() == tmp_path / "cerebrum.sock"

        monkeypatch.setenv("KORTEXT_FALKORDB_SOCKET", str(tmp_path / "kortext.sock"))
        assert get_falkordb_socket() == tmp_path / "kortext.sock"

    def test_get_falkordb_socket_none_when_disabled(self, monkeypatch):
        monkeypatch.setenv("FALKORDB_SOCKET", "none")
        assert get_falkordb_socket() is None

        monkeypatch.setenv("FALKORDB_SOCKET", "disabled")
        assert get_falkordb_socket() is None

    def test_get_falkordb_host_default_and_override(self, monkeypatch):
        monkeypatch.delenv("KORTEXT_FALKORDB_HOST", raising=False)
        monkeypatch.delenv("CEREBRUM_FALKORDB_HOST", raising=False)
        monkeypatch.delenv("FALKORDB_HOST", raising=False)
        assert get_falkordb_host() == "127.0.0.1"

        monkeypatch.setenv("CEREBRUM_FALKORDB_HOST", "192.168.1.10")
        assert get_falkordb_host() == "192.168.1.10"

        monkeypatch.setenv("KORTEXT_FALKORDB_HOST", "10.0.0.1")
        assert get_falkordb_host() == "10.0.0.1"

    def test_get_falkordb_port_default_and_override(self, monkeypatch):
        monkeypatch.delenv("KORTEXT_FALKORDB_PORT", raising=False)
        monkeypatch.delenv("CEREBRUM_FALKORDB_PORT", raising=False)
        monkeypatch.delenv("FALKORDB_PORT", raising=False)
        assert get_falkordb_port() == 6379

        monkeypatch.setenv("CEREBRUM_FALKORDB_PORT", "6380")
        assert get_falkordb_port() == 6380

        monkeypatch.setenv("KORTEXT_FALKORDB_PORT", "6381")
        assert get_falkordb_port() == 6381

    def test_get_falkordb_database_default_and_fallback(self, monkeypatch):
        monkeypatch.delenv("KORTEXT_FALKORDB_DATABASE", raising=False)
        monkeypatch.delenv("CEREBRUM_FALKORDB_DATABASE", raising=False)
        monkeypatch.delenv("FALKORDB_DATABASE", raising=False)
        monkeypatch.delenv("KORTEXT_DATABASE", raising=False)
        monkeypatch.delenv("CEREBRUM_DATABASE", raising=False)
        monkeypatch.delenv("DATABASE", raising=False)
        monkeypatch.delenv("CEREBRUM_HOME", raising=False)
        monkeypatch.delenv("KORTEXT_HOME", raising=False)

        assert get_falkordb_database() == "kortext"

        # Fallback to cerebrum when CEREBRUM_HOME is set without KORTEXT_HOME
        monkeypatch.setenv("CEREBRUM_HOME", "/some/cerebrum")
        assert get_falkordb_database() == "cerebrum"

        # Explicit CEREBRUM_DATABASE overrides CEREBRUM_HOME default
        monkeypatch.setenv("CEREBRUM_DATABASE", "legacy_db")
        assert get_falkordb_database() == "legacy_db"

        # KORTEXT_DATABASE takes precedence
        monkeypatch.setenv("KORTEXT_DATABASE", "custom_kortext_db")
        assert get_falkordb_database() == "custom_kortext_db"

    def test_get_falkordb_symbols_graph_default_and_fallback(self, monkeypatch):
        monkeypatch.delenv("KORTEXT_FALKORDB_SYMBOLS_GRAPH", raising=False)
        monkeypatch.delenv("CEREBRUM_FALKORDB_SYMBOLS_GRAPH", raising=False)
        monkeypatch.delenv("FALKORDB_SYMBOLS_GRAPH", raising=False)
        monkeypatch.delenv("KORTEXT_SYMBOLS_GRAPH", raising=False)
        monkeypatch.delenv("CEREBRUM_SYMBOLS_GRAPH", raising=False)
        monkeypatch.delenv("SYMBOLS_GRAPH", raising=False)
        monkeypatch.delenv("CEREBRUM_HOME", raising=False)
        monkeypatch.delenv("KORTEXT_HOME", raising=False)

        assert get_falkordb_symbols_graph() == "kortext_symbols"

        # Fallback to cerebrum_symbols when CEREBRUM_HOME is set without KORTEXT_HOME
        monkeypatch.setenv("CEREBRUM_HOME", "/some/cerebrum")
        assert get_falkordb_symbols_graph() == "cerebrum_symbols"

        # Explicit CEREBRUM_SYMBOLS_GRAPH overrides
        monkeypatch.setenv("CEREBRUM_SYMBOLS_GRAPH", "legacy_symbols")
        assert get_falkordb_symbols_graph() == "legacy_symbols"

        # KORTEXT_SYMBOLS_GRAPH takes precedence
        monkeypatch.setenv("KORTEXT_SYMBOLS_GRAPH", "custom_kortext_symbols")
        assert get_falkordb_symbols_graph() == "custom_kortext_symbols"

    def test_get_qdrant_url_default_and_override(self, monkeypatch):
        monkeypatch.delenv("KORTEXT_QDRANT_URL", raising=False)
        monkeypatch.delenv("CEREBRUM_QDRANT_URL", raising=False)
        monkeypatch.delenv("QDRANT_URL", raising=False)
        assert get_qdrant_url() == "http://localhost:6333"

        monkeypatch.setenv("CEREBRUM_QDRANT_URL", "http://127.0.0.1:6334")
        assert get_qdrant_url() == "http://127.0.0.1:6334"

        monkeypatch.setenv("KORTEXT_QDRANT_URL", "http://127.0.0.1:6335")
        assert get_qdrant_url() == "http://127.0.0.1:6335"

    def test_get_qdrant_collection_default_and_fallback(self, monkeypatch):
        monkeypatch.delenv("KORTEXT_QDRANT_COLLECTION", raising=False)
        monkeypatch.delenv("CEREBRUM_QDRANT_COLLECTION", raising=False)
        monkeypatch.delenv("QDRANT_COLLECTION", raising=False)
        monkeypatch.delenv("KORTEXT_COLLECTION", raising=False)
        monkeypatch.delenv("CEREBRUM_COLLECTION", raising=False)
        monkeypatch.delenv("COLLECTION", raising=False)
        monkeypatch.delenv("CEREBRUM_HOME", raising=False)
        monkeypatch.delenv("KORTEXT_HOME", raising=False)

        assert get_qdrant_collection() == "kortext_codebase"

        # Fallback to cerebrum_codebase when CEREBRUM_HOME is set without KORTEXT_HOME
        monkeypatch.setenv("CEREBRUM_HOME", "/some/cerebrum")
        assert get_qdrant_collection() == "cerebrum_codebase"

        # Explicit CEREBRUM_QDRANT_COLLECTION overrides
        monkeypatch.setenv("CEREBRUM_QDRANT_COLLECTION", "legacy_codebase")
        assert get_qdrant_collection() == "legacy_codebase"

        # KORTEXT_QDRANT_COLLECTION takes precedence
        monkeypatch.setenv("KORTEXT_QDRANT_COLLECTION", "custom_kortext_codebase")
        assert get_qdrant_collection() == "custom_kortext_codebase"

    def test_get_embed_base_url_default_and_override(self, monkeypatch):
        monkeypatch.delenv("KORTEXT_EMBED_BASE_URL", raising=False)
        monkeypatch.delenv("CEREBRUM_EMBED_BASE_URL", raising=False)
        monkeypatch.delenv("EMBED_BASE_URL", raising=False)
        assert get_embed_base_url() == "http://localhost:8000/v1"

        monkeypatch.setenv("CEREBRUM_EMBED_BASE_URL", "http://localhost:9000/v1")
        assert get_embed_base_url() == "http://localhost:9000/v1"

        monkeypatch.setenv("KORTEXT_EMBED_BASE_URL", "http://localhost:9001/v1")
        assert get_embed_base_url() == "http://localhost:9001/v1"

    def test_get_embed_model_name_default_and_override(self, monkeypatch):
        monkeypatch.delenv("KORTEXT_EMBED_MODEL_NAME", raising=False)
        monkeypatch.delenv("CEREBRUM_EMBED_MODEL_NAME", raising=False)
        monkeypatch.delenv("EMBED_MODEL_NAME", raising=False)
        assert get_embed_model_name() == "mlx-community--Qwen3-Embedding-8B-4bit-DWQ"

        monkeypatch.setenv("CEREBRUM_EMBED_MODEL_NAME", "custom-cerebrum-embed")
        assert get_embed_model_name() == "custom-cerebrum-embed"

        monkeypatch.setenv("KORTEXT_EMBED_MODEL_NAME", "custom-kortext-embed")
        assert get_embed_model_name() == "custom-kortext-embed"

    def test_get_rerank_base_url_default_and_override(self, monkeypatch):
        monkeypatch.delenv("KORTEXT_RERANK_BASE_URL", raising=False)
        monkeypatch.delenv("CEREBRUM_RERANK_BASE_URL", raising=False)
        monkeypatch.delenv("RERANK_BASE_URL", raising=False)
        assert get_rerank_base_url() == "http://localhost:8000/v1"

        monkeypatch.setenv("CEREBRUM_RERANK_BASE_URL", "http://localhost:9002/v1")
        assert get_rerank_base_url() == "http://localhost:9002/v1"

        monkeypatch.setenv("KORTEXT_RERANK_BASE_URL", "http://localhost:9003/v1")
        assert get_rerank_base_url() == "http://localhost:9003/v1"
