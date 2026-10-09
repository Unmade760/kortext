"""
Symbol and file blast-radius impact analysis view builder.
"""
from __future__ import annotations

import os
from pathlib import Path
from typing import Any, Dict, List, Optional

from kortext.dashboard.views.specs import (
    COLOR_HOP2,
    COLOR_HOP3,
    SHADOW_HOP2,
    SHADOW_HOP3,
    _make_vis_edge,
    _make_vis_node,
)


def _get_falkordb_client(host: str, port: int):
    """Facade-aware FalkorDB client resolver preserving backward-compatible mock hooks."""
    import sys
    views_mod = (
        sys.modules.get("kortext.dashboard.views")
        or sys.modules.get("kortext.dashboard.graph_views")
        or sys.modules.get("cerebrum.dashboard.graph_views")
    )
    if views_mod and hasattr(views_mod, "get_shared_falkordb_client"):
        return views_mod.get_shared_falkordb_client(host=host, port=port)
    from kortext.falkordb_client import get_shared_falkordb_client
    return get_shared_falkordb_client(host=host, port=port)


def _get_symbol_graph_manager(graph_name: Optional[str] = None):
    """Facade-aware SymbolGraphManager resolver preserving backward-compatible mock hooks."""
    import sys
    views_mod = (
        sys.modules.get("kortext.dashboard.views")
        or sys.modules.get("kortext.dashboard.graph_views")
        or sys.modules.get("cerebrum.dashboard.graph_views")
    )
    target_graph = graph_name or os.getenv("KORTEXT_SYMBOLS_GRAPH", os.getenv("FALKORDB_SYMBOLS_GRAPH", "kortext_symbols"))
    if views_mod and hasattr(views_mod, "SymbolGraphManager"):
        return views_mod.SymbolGraphManager(graph_name=target_graph)
    from kortext.symbols.graph import SymbolGraphManager
    return SymbolGraphManager(graph_name=target_graph)


def build_symbol_impact_view(
    target: Optional[str],
    file_path: Optional[str],
    symbol: Optional[str],
    direction: str,
    max_depth: int,
    host: str,
    port: int,
    graph_name: Optional[str] = None,
) -> dict:
    """
    Performs blast-radius analysis and formats structured nodes/edges/tree for visualization.
    """
    raw_target = (target or symbol or file_path or "").strip()
    if not raw_target:
        return {"status": "error", "message": "Target symbol or file path is required"}

    depth = max(1, min(int(max_depth), 5))
    is_file = "/" in raw_target or raw_target.endswith((".py", ".ts", ".js", ".go", ".rs", ".cpp", ".c", ".h", ".java"))

    nodes_map: Dict[str, dict] = {}
    edges_list: List[dict] = []
    tree_items: List[dict] = []

    try:
        sym_mgr = _get_symbol_graph_manager(graph_name=graph_name)

        if is_file:
            file_name = Path(raw_target).name
            nodes_map[raw_target] = _make_vis_node(
                node_id=raw_target,
                label=f"🎯  {file_name}",
                group="file",
                level=0,
                title=f"<b>Target File: {file_name}</b><br/>{raw_target}",
            )

            impacts = sym_mgr.get_impact_tree(raw_target)
            for imp in impacts:
                dep_path = imp.get("file_path", "")
                dep_name = Path(dep_path).name
                sym_name = imp.get("symbol", "")
                rel = imp.get("relation", "DEPENDS_ON")
                line = imp.get("line", 1)

                if dep_path not in nodes_map:
                    nodes_map[dep_path] = _make_vis_node(
                        node_id=dep_path,
                        label=f"💥  {dep_name}",
                        group="file",
                        level=1,
                        title=f"<b>Direct Impact: {dep_name}</b><br/>Calls {sym_name} (Line {line})",
                    )

                edges_list.append(
                    _make_vis_edge(
                        dep_path,
                        raw_target,
                        f"{rel} ({sym_name})",
                        color={"color": "#ef4444", "highlight": "#fda4af"},
                        font_color="#f87171",
                        extra_props={"smooth": {"type": "continuous", "roundness": 0.25}},
                    )
                )
                tree_items.append({
                    "file_path": dep_path,
                    "file_name": dep_name,
                    "symbol": sym_name,
                    "relation": rel,
                    "line": line,
                    "risk": "HIGH",
                    "depth": 1,
                })

            summary = {
                "target": raw_target,
                "type": "file",
                "direction": "upstream",
                "direct_impact_count": len(impacts),
                "transitive_count": 0,
                "affected_files_count": len({i.get("file_path") for i in impacts}),
                "risk_level": "HIGH" if len(impacts) > 5 else ("MEDIUM" if impacts else "LOW"),
            }

        else:
            trace = sym_mgr.trace_symbol_impact(raw_target, direction=direction, max_depth=depth)

            nodes_map[raw_target] = _make_vis_node(
                node_id=raw_target,
                label=f"🎯  {raw_target}",
                group="symbol",
                level=0,
                title=f"<b>Target Symbol: {raw_target}</b>",
            )

            for imp in trace.get("direct_impacts", []):
                src_file = imp.get("source_file", "")
                rel = imp.get("relation", "CALLS")
                line = imp.get("line", 1)
                file_label = Path(src_file).name

                if src_file not in nodes_map:
                    nodes_map[src_file] = _make_vis_node(
                        node_id=src_file,
                        label=f"💥  {file_label}",
                        group="file",
                        level=1,
                        title=f"<b>Direct Impact: {file_label}</b><br/>{rel} at line {line}",
                    )

                u_node = src_file if direction.lower() == "upstream" else raw_target
                v_node = raw_target if direction.lower() == "upstream" else src_file
                is_upstream = direction.lower() == "upstream"
                edges_list.append(
                    _make_vis_edge(
                        u_node,
                        v_node,
                        f"{rel}:{line}",
                        color={
                            "color": "#ef4444" if is_upstream else "#38bdf8",
                            "highlight": "#fda4af" if is_upstream else "#7dd3fc",
                        },
                        font_color="#f87171" if is_upstream else "#38bdf8",
                        extra_props={"smooth": {"type": "continuous", "roundness": 0.25}},
                    )
                )

                tree_items.append({
                    "source": src_file,
                    "name": file_label,
                    "relation": rel,
                    "line": line,
                    "risk": "HIGH",
                    "depth": 1,
                })

            for t_item in trace.get("type_hierarchies", []):
                t_sym = t_item.get("symbol", "")
                t_rel = t_item.get("relation", "IMPLEMENTS")
                t_file = t_item.get("file_path", "")

                if t_sym not in nodes_map:
                    nodes_map[t_sym] = _make_vis_node(
                        node_id=t_sym,
                        label=f"⚡  {t_sym}",
                        group="symbol",
                        level=2,
                        title=f"<b>Type Relation: {t_sym}</b><br/>{t_rel} in {Path(t_file).name}",
                    )

                u_node = t_sym if direction.lower() == "upstream" else raw_target
                v_node = raw_target if direction.lower() == "upstream" else t_sym
                edges_list.append(
                    _make_vis_edge(
                        u_node,
                        v_node,
                        t_rel,
                        dashes=[3, 4],
                        color={"color": "#f97316", "highlight": "#fb923c", "hover": "#fed7aa"},
                        font_color="#fb923c",
                        extra_props={
                            "font": {
                                "size": 9,
                                "align": "middle",
                                "color": "#fb923c",
                                "face": "ui-monospace, monospace",
                                "background": "rgba(36, 16, 6, 0.94)",
                            }
                        },
                    )
                )

                tree_items.append({
                    "source": t_sym,
                    "name": t_sym,
                    "relation": t_rel,
                    "file_path": t_file,
                    "risk": "MEDIUM",
                    "depth": 2,
                })

            if depth >= 2:
                client = _get_falkordb_client(host=host, port=port)
                for imp in trace.get("direct_impacts", [])[:10]:
                    sf = imp.get("source_file")
                    trans_q = (
                        "MATCH (f2:File)-[r:IMPORTS]->(s2:Symbol)-[:DEFINED_IN]->(f1:File {path: $p}) "
                        "RETURN DISTINCT f2.path, s2.name, r.line LIMIT 10"
                    )
                    _sym_graph = os.getenv("KORTEXT_SYMBOLS_GRAPH", os.getenv("FALKORDB_SYMBOLS_GRAPH", "kortext_symbols"))
                    t_res = client.query(_sym_graph, trans_q, {"p": sf})
                    if t_res and len(t_res) > 1 and isinstance(t_res[1], list):
                        for r_row in t_res[1]:
                            if len(r_row) >= 3:
                                f2_path = str(r_row[0])
                                f2_name = Path(f2_path).name
                                s2_name = str(r_row[1])
                                if f2_path not in nodes_map and f2_path != sf:
                                    hop2_or_3_font = "#fed7aa" if depth == 2 else "#e0f2fe"
                                    nodes_map[f2_path] = _make_vis_node(
                                        node_id=f2_path,
                                        label=f"🌐  {f2_name}",
                                        group="file",
                                        level=2,
                                        color=COLOR_HOP2 if depth == 2 else COLOR_HOP3,
                                        shadow=SHADOW_HOP2 if depth == 2 else SHADOW_HOP3,
                                        border_width=1.5,
                                        font={"color": hop2_or_3_font, "face": "ui-monospace, monospace", "size": 11, "bold": {"color": hop2_or_3_font}},
                                        title=f"<b>Transitive Consumer: {f2_name}</b><br/>Imports {s2_name}",
                                    )
                                    edges_list.append(
                                        _make_vis_edge(
                                            f2_path,
                                            sf,
                                            f"IMPORTS ({s2_name})",
                                            color={"color": "#64748b", "highlight": "#94a3b8"},
                                            font_color="#94a3b8",
                                            extra_props={
                                                "width": 1.4,
                                                "smooth": {"type": "continuous", "roundness": 0.25},
                                                "font": {
                                                    "size": 8,
                                                    "align": "middle",
                                                    "color": "#94a3b8",
                                                    "face": "ui-monospace, monospace",
                                                    "background": "rgba(15, 23, 42, 0.85)",
                                                },
                                            },
                                        )
                                    )
                                    tree_items.append({
                                        "source": f2_path,
                                        "name": f2_name,
                                        "relation": f"TRANSITIVE IMPORTS ({s2_name})",
                                        "risk": "MEDIUM",
                                        "depth": 2,
                                    })

            summary = {
                "target": raw_target,
                "type": "symbol",
                "direction": direction.lower(),
                "max_depth": depth,
                "definitions_count": len(trace.get("definitions", [])),
                "direct_impact_count": len(trace.get("direct_impacts", [])),
                "type_hierarchy_count": len(trace.get("type_hierarchies", [])),
                "total_impacted_locations": max(0, len(nodes_map) - 1),
                "risk_level": "HIGH" if len(trace.get("direct_impacts", [])) > 4 else ("MEDIUM" if len(nodes_map) > 1 else "LOW"),
            }

        return {
            "status": "ok",
            "target": raw_target,
            "summary": summary,
            "nodes": list(nodes_map.values()),
            "edges": edges_list,
            "tree": tree_items,
        }

    except Exception as e:
        return {"status": "error", "message": str(e), "nodes": [], "edges": [], "tree": []}
