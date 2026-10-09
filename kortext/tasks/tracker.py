"""
Kortext Autonomous Task DAG Tracker.
Graph-backed task state machine with strict dependency gating and failure loops.
"""

from __future__ import annotations

import json
import logging
import uuid
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from kortext.falkordb_client import get_shared_falkordb_client

logger = logging.getLogger("kortext.tasks")


class TaskDAGTracker:
    """Manages Task DAG lifecycle in FalkorDB."""

    def __init__(self, graph_name: str = "kortext"):
        self.client = get_shared_falkordb_client()
        if hasattr(self.client, "resolve_graph_name"):
            self.graph = self.client.resolve_graph_name(graph_name)
        else:
            self.graph = graph_name
        self._ensure_indexes()

    def _ensure_indexes(self) -> None:
        """Ensures FalkorDB schema index on :Task(project_id)."""
        try:
            self.client.query(self.graph, "CREATE INDEX ON :Task(project_id)")
        except Exception as e:
            logger.debug(f"Index creation on :Task(project_id) error: {e}")

    def create_task(
        self,
        title: str,
        description: str,
        complexity: int = 1,
        assigned_to: str = "primary",
        depends_on: Optional[List[str]] = None,
        project_id: Optional[str] = None,
    ) -> str:
        """Creates a new Task node, links it to Project, and sets up dependency edges."""
        task_id = f"task_{uuid.uuid4().hex[:8]}"
        now = datetime.now(timezone.utc).isoformat()
        dep_list = [d for d in (depends_on or []) if d]
        proj_id = project_id or "kortext"

        cypher = """
        MERGE (p:Project {id: $project_id})
        CREATE (t:Task {
            id: $id,
            title: $title,
            description: $desc,
            status: $status,
            complexity: $comp,
            assigned_to: $assign,
            retry_count: 0,
            created_at: $now,
            completed_at: null,
            depends_on: $dep_list,
            project_id: $project_id
        })
        MERGE (p)-[:HAS_TASK]->(t)
        RETURN t.id
        """
        status = "ready" if not dep_list else "pending"
        params = {
            "id": task_id,
            "title": title,
            "desc": description,
            "status": status,
            "comp": complexity,
            "assign": assigned_to,
            "now": now,
            "dep_list": dep_list,
            "project_id": proj_id,
        }
        self.client.query(self.graph, cypher, params)

        if dep_list:
            for dep_id in dep_list:
                dep_cypher = """
                MATCH (t:Task {id: $id}), (dep:Task {id: $dep_id})
                MERGE (t)-[:DEPENDS_ON {strict: true}]->(dep)
                """
                self.client.query(self.graph, dep_cypher, {"id": task_id, "dep_id": dep_id})

        # Wire up any existing tasks that declared dependency on this newly created task
        link_cypher = """
        MATCH (waiting:Task), (new_t:Task {id: $id})
        WHERE $id IN coalesce(waiting.depends_on, [])
        MERGE (waiting)-[:DEPENDS_ON {strict: true}]->(new_t)
        """
        self.client.query(self.graph, link_cypher, {"id": task_id})

        return task_id

    def get_ready_tasks(self, project_id: Optional[str] = None) -> List[Dict[str, Any]]:
        """Finds all tasks whose upstream dependencies are completed."""
        filter_clause = ""
        params: Dict[str, Any] = {}
        if project_id and project_id.lower() != "all":
            filter_clause = "  AND coalesce(t.project_id, 'kortext') = $project_id\n"
            params["project_id"] = project_id

        cypher = f"""
        MATCH (t:Task)
        WHERE t.status IN ['pending', 'ready']
          AND coalesce(size(t.depends_on), 0) = 0
          AND NOT (t)-[:DEPENDS_ON]->(:Task)
        {filter_clause}SET t.status = 'ready'
        RETURN t.id, t.title, t.complexity, t.assigned_to, t.description
        UNION
        MATCH (t:Task)
        WHERE t.status IN ['pending', 'ready']
          AND (t)-[:DEPENDS_ON]->(:Task)
        {filter_clause}WITH t, [(t)-[:DEPENDS_ON]->(dep) | dep.status] AS dep_statuses
        WHERE (t.depends_on IS NULL OR size(dep_statuses) = size(t.depends_on))
          AND ALL(d IN dep_statuses WHERE d = 'completed')
        SET t.status = 'ready'
        RETURN t.id, t.title, t.complexity, t.assigned_to, t.description
        """
        raw = self.client.query(self.graph, cypher, params if params else None)
        if not raw or len(raw) < 2 or not raw[1]:
            return []

        tasks = []
        for row in raw[1]:
            tasks.append({
                "id": row[0],
                "title": row[1],
                "complexity": row[2],
                "assigned_to": row[3],
                "description": row[4],
            })
        return tasks

    def update_task_status(self, task_id: str, status: str, error: Optional[str] = None) -> bool:
        """Updates task state, handles failure retries, and records completion timestamp."""
        now = datetime.now(timezone.utc).isoformat()
        if status == "completed":
            cypher = """
            MATCH (t:Task {id: $id})
            SET t.status = 'completed', t.completed_at = $now
            RETURN t.id
            """
            self.client.query(self.graph, cypher, {"id": task_id, "now": now})
        elif status == "failed":
            cypher = """
            MATCH (t:Task {id: $id})
            SET t.retry_count = t.retry_count + 1,
                t.status = 'failed',
                t.last_error = $err
            RETURN t.status
            """
            self.client.query(self.graph, cypher, {"id": task_id, "err": error or ""})
        else:
            cypher = """
            MATCH (t:Task {id: $id})
            SET t.status = $status
            RETURN t.id
            """
            self.client.query(self.graph, cypher, {"id": task_id, "status": status})
        return True

    def get_all_tasks(self, project_id: Optional[str] = None) -> List[Dict[str, Any]]:
        """Returns all Task nodes with metadata and their dependencies."""
        where_clause = ""
        params: Dict[str, Any] = {}
        if project_id and project_id.lower() != "all":
            where_clause = "WHERE coalesce(t.project_id, 'kortext') = $project_id\n        "
            params["project_id"] = project_id

        cypher = f"""
        MATCH (t:Task)
        {where_clause}OPTIONAL MATCH (t)-[:DEPENDS_ON]->(dep:Task)
        RETURN t.id, t.title, t.description, t.status, t.complexity, t.assigned_to,
               t.retry_count, t.created_at, t.completed_at, t.last_error, collect(dep.id),
               coalesce(t.project_id, 'kortext')
        ORDER BY t.created_at DESC
        """
        raw = self.client.query(self.graph, cypher, params if params else None)
        if not raw or len(raw) < 2 or not raw[1]:
            return []

        tasks = []
        for row in raw[1]:
            deps = []
            if isinstance(row[10], list):
                deps = [d for d in row[10] if d]
            elif isinstance(row[10], str) and row[10]:
                cleaned = row[10].strip("[]").replace("'", "").replace('"', "")
                deps = [d.strip() for d in cleaned.split(",") if d.strip()]

            tasks.append({
                "id": str(row[0]),
                "title": str(row[1]),
                "description": str(row[2] or ""),
                "status": str(row[3] or "pending"),
                "complexity": int(row[4] or 1),
                "assigned_to": str(row[5] or "primary"),
                "retry_count": int(row[6] or 0),
                "created_at": str(row[7] or ""),
                "completed_at": str(row[8] or "") if row[8] is not None else None,
                "last_error": str(row[9] or "") if row[9] is not None else None,
                "depends_on": deps,
                "project_id": str(row[11]) if len(row) > 11 and row[11] is not None else "kortext",
            })
        return tasks

    def link_task_to_outcome(self, task_id: str, episode_name: str) -> bool:
        """Links a completed Task node to an Episodic outcome node."""
        cypher = """
        MATCH (t:Task {id: $task_id}), (e:Episodic {name: $episode_name})
        MERGE (t)-[:PRODUCED_OUTCOME]->(e)
        RETURN count(e)
        """
        raw = self.client.query(
            self.graph,
            cypher,
            {"task_id": task_id, "episode_name": episode_name},
        )
        if not raw or len(raw) < 2 or not raw[1]:
            return False
        try:
            return int(raw[1][0][0]) > 0
        except (ValueError, TypeError, IndexError):
            return False

    def get_graph_data(self, project_id: Optional[str] = None) -> Dict[str, Any]:
        """Formats all tasks into nodes and edges for Vis.js rendering."""
        tasks = self.get_all_tasks(project_id=project_id)
        nodes = []
        edges = []
        status_styles = {
            "completed": {
                "background": "#022c22",
                "border": "#10b981",
                "highlight": {"background": "#064e3b", "border": "#34d399"},
                "icon": "✓",
            },
            "ready": {
                "background": "#082f49",
                "border": "#38bdf8",
                "highlight": {"background": "#0c4a6e", "border": "#7dd3fc"},
                "icon": "▶",
            },
            "in_progress": {
                "background": "#2a1406",
                "border": "#f97316",
                "highlight": {"background": "#3d1d09", "border": "#fb923c"},
                "icon": "⚡",
                "fontColor": "#fed7aa",
            },
            "pending": {
                "background": "#0f172a",
                "border": "#64748b",
                "highlight": {"background": "#1e293b", "border": "#94a3b8"},
                "icon": "⏳",
                "fontColor": "#cbd5e1",
            },
            "failed": {
                "background": "#450a0a",
                "border": "#f87171",
                "highlight": {"background": "#7f1d1d", "border": "#fca5a5"},
                "icon": "❌",
                "fontColor": "#fecaca",
            },
            "blocked": {
                "background": "#3b0764",
                "border": "#e11d48",
                "highlight": {"background": "#581c87", "border": "#fb7185"},
                "icon": "🔒",
                "fontColor": "#fecdd3",
            },
        }
        for t in tasks:
            st = t["status"]
            style = status_styles.get(st, {
                "background": "#1e1b4b",
                "border": "#6366f1",
                "highlight": {"background": "#312e81", "border": "#818cf8"},
                "icon": "•",
                "fontColor": "#e0e7ff",
            })
            icon = style["icon"]
            title_display = t["title"][:28] + ("..." if len(t["title"]) > 28 else "")

            nodes.append({
                "id": t["id"],
                "label": f"<b>{icon} {t['id']}</b>\n{title_display}",
                "title": f"<b>{t['title']}</b><br/>Status: <span style='text-transform:uppercase;color:#38bdf8;'>{st}</span><br/>Complexity: {t['complexity']}/10<br/>Assigned: {t['assigned_to']}",
                "color": {
                    "background": style["background"],
                    "border": style["border"],
                    "highlight": style["highlight"],
                },
                "shape": "box",
                "margin": 10,
                "borderWidth": 2,
                "borderWidthSelected": 3,
                "shadow": {
                    "enabled": True,
                    "color": "rgba(0, 0, 0, 0.7)",
                    "size": 12,
                    "x": 2,
                    "y": 4,
                },
                "font": {
                    "color": style.get("fontColor", "#f8fafc"),
                    "bold": {"color": style.get("fontColor", "#f8fafc")},
                    "face": "ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, monospace",
                    "size": 11,
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
                    "arrows": {
                        "to": {"enabled": True, "scaleFactor": 0.8},
                    },
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

