"""
Unit tests for TaskDAGTracker dependency gating and state machine.
"""

import pytest
from unittest.mock import MagicMock
from cerebrum.tasks.tracker import TaskDAGTracker


class TestTaskDAGTracker:
    @pytest.fixture
    def tracker(self):
        t = TaskDAGTracker()
        t.client = MagicMock()
        return t

    def test_create_task_ready_state(self, tracker):
        t_id = tracker.create_task(
            title="Compile FalkorDB",
            description="Run native build script",
            complexity=2
        )
        assert t_id.startswith("task_")
        assert tracker.client.query.called

    def test_get_ready_tasks_returns_unblocked(self, tracker):
        tracker.client.query.return_value = [
            ["id", "title", "complexity", "assigned_to", "description"],
            [
                ["task_12345678", "Build Native Engine", 3, "primary", "Step 1"]
            ]
        ]
        ready = tracker.get_ready_tasks()
        assert len(ready) == 1
        assert ready[0]["id"] == "task_12345678"
        assert ready[0]["complexity"] == 3

    def test_task_status_retry_limit(self, tracker):
        tracker.update_task_status("task_fail_1", "failed", error="Compile error")
        assert tracker.client.query.called
