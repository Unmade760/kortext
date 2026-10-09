"""Kortext: Local RAG, 5-tier dual-memory, AST code intelligence, and task DAG knowledge OS for Antigravity CLI."""

from kortext._home import KORTEXT_HOME, get_kortext_home
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
from kortext._qdrant import (
    get_qdrant_client,
    get_sync_qdrant_client,
    get_async_qdrant_client,
    is_qdrant_online,
)
from kortext.embeddings import (
    DenseEmbedder,
    DenseEmbedderProtocol,
    FastEmbedDenseProvider,
    RemoteDenseProvider,
    get_dense_embedder,
    is_remote_embed_alive,
)

CEREBRUM_HOME = KORTEXT_HOME


import importlib
import importlib.abc
import importlib.machinery
import sys


class _AliasLoader(importlib.abc.Loader):
    def __init__(self, target_module):
        self.target_module = target_module

    def create_module(self, spec):
        return self.target_module

    def exec_module(self, module):
        pass


class _CerebrumAliasFinder(importlib.abc.MetaPathFinder):
    def find_spec(self, fullname, path, target=None):
        if fullname == "cerebrum" or fullname.startswith("cerebrum."):
            kortext_name = "kortext" + fullname[len("cerebrum"):]
            mod = importlib.import_module(kortext_name)
            sys.modules[fullname] = mod
            is_pkg = hasattr(mod, "__path__")
            return importlib.machinery.ModuleSpec(fullname, _AliasLoader(mod), is_package=is_pkg)
        return None


if not any(isinstance(f, _CerebrumAliasFinder) for f in sys.meta_path):
    sys.meta_path.insert(0, _CerebrumAliasFinder())

if "kortext" in sys.modules and "cerebrum" not in sys.modules:
    sys.modules["cerebrum"] = sys.modules["kortext"]
elif "cerebrum" in sys.modules and "kortext" not in sys.modules:
    sys.modules["kortext"] = sys.modules["cerebrum"]
