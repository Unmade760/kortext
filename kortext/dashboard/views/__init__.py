"""
Views package for graph visualizations and impact analysis.
"""
from __future__ import annotations

from kortext.dashboard.views.impact import build_symbol_impact_view
from kortext.dashboard.views.overview import (
    _handle_defined_in,
    _handle_doc_links,
    _handle_filter_existing,
    _handle_symbol_hierarchy,
    _handle_tags,
    _infer_cluster,
    build_graph_view,
    populate_clean_symbols_graph,
)
from kortext.dashboard.views.specs import (
    COLOR_HOP1,
    COLOR_HOP2,
    COLOR_HOP3,
    COLOR_TARGET,
    DEFAULT_REL_SPEC,
    EDGE_STYLES,
    NODE_LEVEL_SPECS,
    REL_SPECS,
    SHADOW_HOP1,
    SHADOW_HOP2,
    SHADOW_HOP3,
    SHADOW_TARGET,
    _make_vis_edge,
    _make_vis_node,
)
from kortext.falkordb_client import get_shared_falkordb_client
from kortext.symbols.graph import SymbolGraphManager

__all__ = [
    "DEFAULT_REL_SPEC",
    "EDGE_STYLES",
    "REL_SPECS",
    "NODE_LEVEL_SPECS",
    "COLOR_TARGET",
    "COLOR_HOP1",
    "COLOR_HOP2",
    "COLOR_HOP3",
    "SHADOW_TARGET",
    "SHADOW_HOP1",
    "SHADOW_HOP2",
    "SHADOW_HOP3",
    "_make_vis_edge",
    "_make_vis_node",
    "_handle_defined_in",
    "_handle_filter_existing",
    "_handle_symbol_hierarchy",
    "_handle_doc_links",
    "_handle_tags",
    "populate_clean_symbols_graph",
    "_infer_cluster",
    "build_graph_view",
    "build_symbol_impact_view",
    "get_shared_falkordb_client",
    "SymbolGraphManager",
]
