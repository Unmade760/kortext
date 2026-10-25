"""
Kortext symbols package: deterministic code symbol and cross-file reference graph.
"""
from typing import Any
from .formatter import format_impact_report
from .markdown_extractor import MarkdownSymbolExtractor

__all__ = [
    "SymbolGraphManager",
    "MarkdownSymbolExtractor",
    "SymbolSeekEngine",
    "extract_symbol_candidates",
    "_extract_symbol_candidates",
    "format_impact_report",
]


def __getattr__(name: str) -> Any:
    if name == "SymbolGraphManager":
        from .graph import SymbolGraphManager
        return SymbolGraphManager
    if name in ("SymbolSeekEngine", "extract_symbol_candidates", "_extract_symbol_candidates"):
        from . import seek as _seek
        return getattr(_seek, name)
    raise AttributeError(f"module 'kortext.symbols' has no attribute {name!r}")

