"""
Unit tests for Task DAG Project nodes and indexed project scoping isolation.
"""

from __future__ import annotations

import uuid
from typing import Generator
import pytest

from kortext.tasks.tracker import TaskDAGTracker


@pytest.fixture
def isolated_tracker() -> Generator[TaskDAGTracker, None, None]:
    """Provides a TaskDAGTracker instance connected to an isolated test graph."""
    graph_name = f"test_task_dag_iso_{uuid.uuid4().hex[:8]}"
    tracker = TaskDAGTracker(graph_name=graph_name)
    yield tracker
    try:
        tracker.client.get_redis().execute_command("GRAPH.DELETE", tracker.graph)
    except Exception:
        pass


class TestTaskDAGIsolation:
    def test_project_scoping_isolation(self, isolated_tracker: TaskDAGTracker) -> None:
        """
        Test 1: create tasks under project 'proj_alpha' and 'proj_beta'.
        Verify get_ready_tasks('proj_alpha') only returns tasks belonging to 'proj_alpha'.
        """
        t_alpha = isolated_tracker.create_task(
            title="Task Alpha 1",
            description="Alpha task description",
            complexity=2,
            project_id="proj_alpha",
        )
        t_beta = isolated_tracker.create_task(
            title="Task Beta 1",
            description="Beta task description",
            complexity=3,
            project_id="proj_beta",
        )

        ready_alpha = isolated_tracker.get_ready_tasks(project_id="proj_alpha")
        alpha_ids = [t["id"] for t in ready_alpha]
        assert t_alpha in alpha_ids
        assert t_beta not in alpha_ids

        ready_beta = isolated_tracker.get_ready_tasks(project_id="proj_beta")
        beta_ids = [t["id"] for t in ready_beta]
        assert t_beta in beta_ids
        assert t_alpha not in beta_ids

    def test_get_ready_tasks_all_projects(self, isolated_tracker: TaskDAGTracker) -> None:
        """
        Test 2: get_ready_tasks('all') returns tasks across both projects.
        """
        t_alpha = isolated_tracker.create_task(
            title="Task Alpha Global",
            description="Alpha task",
            project_id="proj_alpha",
        )
        t_beta = isolated_tracker.create_task(
            title="Task Beta Global",
            description="Beta task",
            project_id="proj_beta",
        )

        ready_all = isolated_tracker.get_ready_tasks(project_id="all")
        all_ids = [t["id"] for t in ready_all]
        assert t_alpha in all_ids
        assert t_beta in all_ids

        ready_all_upper = isolated_tracker.get_ready_tasks(project_id="ALL")
        all_upper_ids = [t["id"] for t in ready_all_upper]
        assert t_alpha in all_upper_ids
        assert t_beta in all_upper_ids

    def test_link_task_to_outcome(self, isolated_tracker: TaskDAGTracker) -> None:
        """
        Test 3: link_task_to_outcome() creates [:PRODUCED_OUTCOME] edge between Task and Episodic nodes.
        """
        t_id = isolated_tracker.create_task(
            title="Execution Task",
            description="Generate artifact",
            project_id="proj_alpha",
        )
        episode_name = f"episode_{uuid.uuid4().hex[:8]}"

        # Create Episodic node in graph
        isolated_tracker.client.query(
            isolated_tracker.graph,
            "CREATE (:Episodic {name: $name, summary: 'Task outcome recorded'})",
            {"name": episode_name},
        )

        # Link task to outcome
        linked = isolated_tracker.link_task_to_outcome(task_id=t_id, episode_name=episode_name)
        assert linked is True

        # Verify edge exists in FalkorDB
        edge_query = """
        MATCH (t:Task {id: $task_id})-[r:PRODUCED_OUTCOME]->(e:Episodic {name: $episode_name})
        RETURN count(r)
        """
        res = isolated_tracker.client.query(
            isolated_tracker.graph,
            edge_query,
            {"task_id": t_id, "episode_name": episode_name},
        )
        assert res and len(res) >= 2 and res[1][0][0] == 1

        # Nonexistent episode or task returns False
        assert isolated_tracker.link_task_to_outcome(task_id="nonexistent_task", episode_name=episode_name) is False
        assert isolated_tracker.link_task_to_outcome(task_id=t_id, episode_name="nonexistent_episode") is False

    def test_project_nodes_and_has_task_relationship(self, isolated_tracker: TaskDAGTracker) -> None:
        """Verifies Project node is merged and [:HAS_TASK] edge is created."""
        t_id = isolated_tracker.create_task(
            title="Project Relation Task",
            description="Check Project node",
            project_id="custom_project",
        )
        res = isolated_tracker.client.query(
            isolated_tracker.graph,
            "MATCH (p:Project {id: $proj_id})-[:HAS_TASK]->(t:Task {id: $task_id}) RETURN p.id, t.project_id",
            {"proj_id": "custom_project", "task_id": t_id},
        )
        assert res and len(res) >= 2 and len(res[1]) == 1
        assert res[1][0][0] == "custom_project"
        assert res[1][0][1] == "custom_project"

    def test_get_all_tasks_project_filtering(self, isolated_tracker: TaskDAGTracker) -> None:
        """Verifies get_all_tasks() filters by project_id when specified."""
        t_alpha = isolated_tracker.create_task(
            title="Task A",
            description="Proj A",
            project_id="proj_alpha",
        )
        t_beta = isolated_tracker.create_task(
            title="Task B",
            description="Proj B",
            project_id="proj_beta",
        )

        all_alpha = isolated_tracker.get_all_tasks(project_id="proj_alpha")
        alpha_ids = [t["id"] for t in all_alpha]
        assert t_alpha in alpha_ids
        assert t_beta not in alpha_ids

        all_both = isolated_tracker.get_all_tasks(project_id="all")
        both_ids = [t["id"] for t in all_both]
        assert t_alpha in both_ids
        assert t_beta in both_ids

    def test_default_project_fallback_to_kortext(self, isolated_tracker: TaskDAGTracker) -> None:
        """Verifies tasks created without project_id default to 'kortext'."""
        t_default = isolated_tracker.create_task(
            title="Default Task",
            description="Default project task",
        )
        ready_kortext = isolated_tracker.get_ready_tasks(project_id="kortext")
        assert t_default in [t["id"] for t in ready_kortext]

        all_tasks = isolated_tracker.get_all_tasks()
        task_data = next(t for t in all_tasks if t["id"] == t_default)
        assert task_data["project_id"] == "kortext"

    def test_ensure_indexes_execution(self, isolated_tracker: TaskDAGTracker) -> None:
        """Verifies _ensure_indexes executes without error."""
        # Calling _ensure_indexes explicitly should be idempotent
        isolated_tracker._ensure_indexes()
        assert isolated_tracker.client is not None
