import json
from pathlib import Path
import pytest
from kortext.handoff import HandoffManager


def test_handoff_manager_create(tmp_path: Path):
    mgr = HandoffManager(tmp_path)
    res = mgr.create_baton(
        target_agent="claude-code",
        current_scope="test scope",
        open_hypotheses=["h1"],
        unresolved_questions=["q1"],
        active_blast_radius=["file1.py"],
    )
    assert "Created cross-agent handoff baton" in res
    assert "claude-code" in res
    assert "test scope" in res

    files = list(tmp_path.glob("baton_*.json"))
    assert len(files) == 1
    data = json.loads(files[0].read_text(encoding="utf-8"))
    assert data["target_agent"] == "claude-code"
    assert data["current_scope"] == "test scope"
    assert data["open_hypotheses"] == ["h1"]
    assert data["unresolved_questions"] == ["q1"]
    assert data["active_blast_radius"] == ["file1.py"]
    assert data["status"] == "pending"


def test_handoff_manager_read_and_list(tmp_path: Path):
    mgr = HandoffManager(tmp_path)

    # Empty dir read
    empty_res = mgr.read_baton()
    assert "No cross-agent handoff batons found" in empty_res

    # Create two batons
    mgr.create_baton(target_agent="agent_a", current_scope="scope_a")
    mgr.create_baton(target_agent="agent_b", current_scope="scope_b")

    # List
    list_res = json.loads(mgr.list_batons())
    assert len(list_res["pending_batons"]) == 2

    # Read by target agent
    read_a = json.loads(mgr.read_baton(target_agent="agent_a"))
    assert read_a["target_agent"] == "agent_a"
    assert read_a["current_scope"] == "scope_a"

    # Read by specific baton id
    baton_b_id = list_res["pending_batons"][0]["baton_id"]
    read_b = json.loads(mgr.read_baton(baton_id=baton_b_id))
    assert read_b["baton_id"] == baton_b_id

    # Read non-existent
    not_found = mgr.read_baton(baton_id="non_existent_id")
    assert "No matching handoff baton found" in not_found


def test_handoff_manager_complete(tmp_path: Path):
    mgr = HandoffManager(tmp_path)

    # Missing baton_id
    assert "Please provide baton_id" in mgr.complete_baton(None)

    # Baton not found
    assert "not found" in mgr.complete_baton("non_existent_id")

    # Create and complete
    mgr.create_baton(target_agent="agent_c", current_scope="scope_c")
    list_res = json.loads(mgr.list_batons())
    bid = list_res["pending_batons"][0]["baton_id"]

    res_comp = mgr.complete_baton(bid)
    assert "marked as completed" in res_comp

    baton_file = tmp_path / f"{bid}.json"
    data = json.loads(baton_file.read_text(encoding="utf-8"))
    assert data["status"] == "completed"
    assert "completed_at" in data


def test_handoff_manager_execute_dispatch(tmp_path: Path):
    mgr = HandoffManager(tmp_path)

    create_out = mgr.execute(action="create", target_agent="test_agent")
    assert "Created cross-agent handoff baton" in create_out

    list_out = mgr.execute(action="list")
    assert "pending_batons" in list_out
    bid = json.loads(list_out)["pending_batons"][0]["baton_id"]

    read_out = mgr.execute(action="read", baton_id=bid)
    assert bid in read_out

    complete_out = mgr.execute(action="complete", baton_id=bid)
    assert "marked as completed" in complete_out

    unknown_out = mgr.execute(action="invalid_action")
    assert "Unknown action" in unknown_out
