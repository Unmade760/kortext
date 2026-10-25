"""
Tree-sitter Language Grammars and Extension Mappings for Kortext.

Supports 10 core language ecosystems across Tier 1 (Modern Web/Systems)
and Tier 2 (Enterprise, Native & Systems), with lazy on-demand grammar loading
to eliminate cold-start import overhead in CLI hooks.
"""
from __future__ import annotations

import importlib
import logging
from typing import Any, Callable, Dict, Iterator, Optional, Set

logger = logging.getLogger(__name__)

# Tree-sitter bindings
try:
    from tree_sitter import Language, Node as TSNode, Parser
    _TS_AVAILABLE = True
except ImportError:
    Language = Any  # type: ignore
    TSNode = Any    # type: ignore
    Parser = Any    # type: ignore
    _TS_AVAILABLE = False


_EXT_LOADERS: Dict[str, tuple[str, str]] = {
    ".py": ("tree_sitter_python", "language"),
    ".js": ("tree_sitter_javascript", "language"),
    ".jsx": ("tree_sitter_javascript", "language"),
    ".ts": ("tree_sitter_typescript", "language_typescript"),
    ".tsx": ("tree_sitter_typescript", "language_tsx"),
    ".rs": ("tree_sitter_rust", "language"),
    ".go": ("tree_sitter_go", "language"),
    ".c": ("tree_sitter_c", "language"),
    ".h": ("tree_sitter_c", "language"),
    ".cpp": ("tree_sitter_cpp", "language"),
    ".hpp": ("tree_sitter_cpp", "language"),
    ".cc": ("tree_sitter_cpp", "language"),
    ".cxx": ("tree_sitter_cpp", "language"),
    ".java": ("tree_sitter_java", "language"),
    ".kt": ("tree_sitter_kotlin", "language"),
    ".kts": ("tree_sitter_kotlin", "language"),
    ".swift": ("tree_sitter_swift", "language"),
    ".cs": ("tree_sitter_c_sharp", "language"),
}


class _LazyLangMap(dict):
    """
    Lazy dictionary mapping file extensions (e.g. '.py') to Tree-sitter Language objects.
    Loads each compiled grammar C-extension on first access rather than at module import time.
    """

    def __init__(self) -> None:
        super().__init__()
        self._failed: Set[str] = set()

    def _resolve_ext(self, ext: str) -> Optional[Any]:
        if not _TS_AVAILABLE or ext in self._failed:
            return None
        if super().__contains__(ext):
            return super().__getitem__(ext)
        spec = _EXT_LOADERS.get(ext)
        if not spec:
            return None
        mod_name, fn_name = spec
        try:
            mod = importlib.import_module(mod_name)
            lang_fn: Callable[[], Any] = getattr(mod, fn_name)
            lang_obj = Language(lang_fn())
            super().__setitem__(ext, lang_obj)
            return lang_obj
        except Exception:
            self._failed.add(ext)
            return None

    def _ensure_all_loaded(self) -> None:
        for ext in _EXT_LOADERS:
            if not super().__contains__(ext) and ext not in self._failed:
                self._resolve_ext(ext)

    def __getitem__(self, key: str) -> Any:
        if super().__contains__(key):
            return super().__getitem__(key)
        val = self._resolve_ext(key)
        if val is not None:
            return val
        raise KeyError(key)

    def get(self, key: str, default: Any = None) -> Any:
        if super().__contains__(key):
            return super().__getitem__(key)
        val = self._resolve_ext(key)
        return val if val is not None else default

    def __contains__(self, key: object) -> bool:
        if not isinstance(key, str):
            return False
        if super().__contains__(key):
            return True
        return self._resolve_ext(key) is not None

    def keys(self):  # type: ignore[override]
        self._ensure_all_loaded()
        return super().keys()

    def values(self):  # type: ignore[override]
        self._ensure_all_loaded()
        return super().values()

    def items(self):  # type: ignore[override]
        self._ensure_all_loaded()
        return super().items()

    def __iter__(self) -> Iterator[str]:
        self._ensure_all_loaded()
        return super().__iter__()

    def __len__(self) -> int:
        self._ensure_all_loaded()
        return super().__len__()


LANG_MAP: Dict[str, Language] = _LazyLangMap()


def __getattr__(name: str) -> Any:
    alias_map = {
        "PY_LANG": ".py",
        "JS_LANG": ".js",
        "TS_LANG": ".ts",
        "TSX_LANG": ".tsx",
        "RUST_LANG": ".rs",
        "GO_LANG": ".go",
    }
    if name in alias_map:
        return LANG_MAP.get(alias_map[name])
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")


# Canonical extensions
SUPPORTED_CODE_EXTS: Set[str] = set(_EXT_LOADERS.keys())
SUPPORTED_CONFIG_EXTS: Set[str] = {".yaml", ".yml", ".json", ".toml"}
SUPPORTED_DOC_EXTS: Set[str] = {".md", ".markdown", ".txt"}
ALL_SUPPORTED_EXTS: Set[str] = (
    SUPPORTED_CODE_EXTS
    | SUPPORTED_CONFIG_EXTS
    | SUPPORTED_DOC_EXTS
)


def print_language_status():
    """Prints the status of all supported Tree-sitter language grammars."""
    all_langs = [
        ("Python", [".py"], "tree-sitter-python"),
        ("JavaScript / TypeScript", [".js", ".jsx", ".ts", ".tsx"], "tree-sitter-javascript, tree-sitter-typescript"),
        ("Rust", [".rs"], "tree-sitter-rust"),
        ("Go", [".go"], "tree-sitter-go"),
        ("C", [".c", ".h"], "tree-sitter-c"),
        ("C++", [".cpp", ".hpp", ".cc", ".cxx"], "tree-sitter-cpp"),
        ("Java", [".java"], "tree-sitter-java"),
        ("Kotlin", [".kt", ".kts"], "tree-sitter-kotlin"),
        ("Swift", [".swift"], "tree-sitter-swift"),
        ("C#", [".cs"], "tree-sitter-c-sharp"),
    ]
    print("\n=== Kortext Tree-sitter Language Support Status ===")
    print(f"{'Language Family':<26} {'Extensions':<24} {'Status':<12}")
    print("-" * 64)
    for name, exts, _ in all_langs:
        is_active = any(ext in LANG_MAP for ext in exts)
        status_str = "✅ Active" if is_active else "⚪ Inactive"
        exts_str = ", ".join(exts)
        print(f"{name:<26} {exts_str:<24} {status_str:<12}")
    print("-" * 64)
