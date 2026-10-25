"""
Vis.js Graph Formatting Helper for Kortext Task DAG Tracker.
"""

from __future__ import annotations

import html
from typing import Any, Dict, List

STATUS_STYLES: Dict[str, Dict[str, Any]] = {
    "completed": {
        "background": "#0a0f1d",
        "border": "#10b981",
        "highlight": {"background": "#1e293b", "border": "#ffffff"},
        "icon": "✓",
    },
    "ready": {
        "background": "#0a0f1d",
        "border": "#38bdf8",
        "highlight": {"background": "#1e293b", "border": "#ffffff"},
        "icon": "▶",
    },
    "in_progress": {
        "background": "#0a0f1d",
        "border": "#f59e0b",
        "highlight": {"background": "#1e293b", "border": "#ffffff"},
        "icon": "⚡",
    },
    "pending": {
        "background": "#0a0f1d",
        "border": "#64748b",
        "highlight": {"background": "#1e293b", "border": "#ffffff"},
        "icon": "⏳",
    },
    "failed": {
        "background": "#0a0f1d",
        "border": "#f87171",
        "highlight": {"background": "#1e293b", "border": "#ffffff"},
        "icon": "❌",
    },
    "blocked": {
        "background": "#0a0f1d",
        "border": "#e11d48",
        "highlight": {"background": "#1e293b", "border": "#ffffff"},
        "icon": "🔒",
    },
}

DEFAULT_STYLE: Dict[str, Any] = {
    "background": "#0a0f1d",
    "border": "#6366f1",
    "highlight": {"background": "#1e293b", "border": "#ffffff"},
    "icon": "•",
}


def format_visjs_graph_data(tasks: List[Dict[str, Any]]) -> Dict[str, Any]:
    """Formats Task DAG nodes and dependency edges for Vis.js dashboard rendering."""
    nodes: List[Dict[str, Any]] = []
    edges: List[Dict[str, Any]] = []
    for t in tasks:
        st = t["status"]
        style = STATUS_STYLES.get(st, DEFAULT_STYLE)
        icon = style["icon"]
        raw_title = t["title"]
        title_display = html.escape(raw_title[:28] + ("..." if len(raw_title) > 28 else ""))
        safe_id = html.escape(str(t["id"]))
        safe_title = html.escape(raw_title)
        safe_st = html.escape(str(st))
        safe_assigned = html.escape(str(t["assigned_to"]))

        nodes.append({
            "id": t["id"],
            "label": f"<b>{icon} {safe_id}</b>\n{title_display}",
            "title": (
                f"<b>{safe_title}</b><br/>"
                f"Status: <span style='text-transform:uppercase;color:#38bdf8;'>{safe_st}</span><br/>"
                f"Complexity: {int(t['complexity'])}/10<br/>"
                f"Assigned: {safe_assigned}"
            ),
            "color": {
                "background": style["background"],
                "border": style["border"],
                "highlight": style["highlight"],
            },
            "shape": "box",
            "margin": 10,
            "borderWidth": 2,
            "borderWidthSelected": 2.5,
            "shadow": {
                "enabled": True,
                "color": "rgba(0, 0, 0, 0.7)",
                "size": 12,
                "x": 2,
                "y": 4,
            },
            "font": {
                "color": "#ffffff",
                "bold": {"color": "#ffffff"},
                "face": "ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, monospace",
                "size": 12,
                "multi": "html",
            },
            "status": st,
            "complexity": t["complexity"],
            "assigned_to": t["assigned_to"],
            "description": t["description"],
            "created_at": t["created_at"],
            "completed_at": t["completed_at"],
        })
        for dep in t["depends_on"]:
            edges.append({
                "from": t["id"],
                "to": dep,
                "arrows": {"to": {"enabled": True, "scaleFactor": 0.8}},
                "label": "depends on",
                "font": {
                    "size": 9,
                    "color": "#fb7185",
                    "face": "ui-monospace, monospace",
                    "align": "middle",
                    "background": "rgba(36, 8, 14, 0.94)",
                },
                "color": {
                    "color": "#f43f5e",
                    "highlight": "#fb7185",
                    "hover": "#fda4af",
                    "opacity": 0.9,
                },
                "width": 2.0,
                "smooth": {"type": "continuous", "roundness": 0.28},
                "shadow": {
                    "enabled": True,
                    "color": "rgba(244, 63, 94, 0.25)",
                    "size": 6,
                    "x": 0,
                    "y": 2,
                },
            })
    return {"nodes": nodes, "edges": edges, "tasks": tasks}
