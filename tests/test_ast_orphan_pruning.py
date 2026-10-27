"""
Unit tests for AST symbol orphan pruning in SymbolGraphManager.save_file_ast.
"""
from __future__ import annotations

import uuid
import pytest
from kortext.symbols.graph import SymbolGraphManager
from kortext.falkordb_client import get_shared_falkordb_client


@pytest.fixture
def temp_graph_manager():
    client = get_shared_falkordb_client()
    try:
        client.get_redis().ping()
    except Exception as exc:
        pytest.skip(f"FalkorDB is offline: {exc}")

    graph_name = f"test_orphan_{uuid.uuid4().hex[:8]}"
    mgr = SymbolGraphManager(graph_name=graph_name, client=client)
    yield mgr
    try:
        mgr.clear()
        client.get_redis().execute_command("GRAPH.DELETE", graph_name)
    except Exception:
        pass


def test_ast_orphan_pruning_removes_deleted_symbol(temp_graph_manager):
    """
    Test 1: Save AST for a file with declarations func_one and func_two.
    Verify both exist. Re-save AST for the same file with only func_one.
    Verify func_two Symbol node is completely deleted from the graph.
    """
    file_path = "src/module.py"
    decls_initial = [
        {"name": "func_one", "kind": "function", "line": 10},
        {"name": "func_two", "kind": "function", "line": 20},
    ]
    temp_graph_manager.save_file_ast(file_path, decls_initial, [], [])

    # Verify both exist
    defs_one = temp_graph_manager.find_definition("func_one")
    defs_two = temp_graph_manager.find_definition("func_two")
    assert len(defs_one) == 1
    assert len(defs_two) == 1

    # Verify Symbol nodes exist in graph
    res = temp_graph_manager._query("MATCH (s:Symbol) RETURN s.name")
    sym_names = [row[0] for row in res[1]] if len(res) > 1 and res[1] else []
    assert "func_one" in sym_names
    assert "func_two" in sym_names

    # Re-save AST for the same file with only func_one
    decls_updated = [
        {"name": "func_one", "kind": "function", "line": 10},
    ]
    temp_graph_manager.save_file_ast(file_path, decls_updated, [], [])

    # Verify func_one still exists
    defs_one_updated = temp_graph_manager.find_definition("func_one")
    assert len(defs_one_updated) == 1

    # Verify func_two Symbol node is completely deleted from the graph
    defs_two_updated = temp_graph_manager.find_definition("func_two")
    assert len(defs_two_updated) == 0

    res_after = temp_graph_manager._query("MATCH (s:Symbol {name: 'func_two'}) RETURN s.name")
    rows_after = res_after[1] if len(res_after) > 1 and res_after[1] else []
    assert len(rows_after) == 0


def test_ast_orphan_pruning_preserves_shared_symbol(temp_graph_manager):
    """
    Test 2: If func_shared is defined in file A and file B, removing it from file A
    does NOT delete func_shared because it is still defined in file B.
    """
    file_a = "src/module_a.py"
    file_b = "src/module_b.py"

    temp_graph_manager.save_file_ast(
        file_a,
        [{"name": "func_shared", "kind": "function", "line": 10}],
        [],
        [],
    )
    temp_graph_manager.save_file_ast(
        file_b,
        [{"name": "func_shared", "kind": "function", "line": 25}],
        [],
        [],
    )

    # Verify defined in both
    defs = temp_graph_manager.find_definition("func_shared")
    assert len(defs) == 2
    paths = {d["file_path"] for d in defs}
    assert paths == {file_a, file_b}

    # Re-save file A without func_shared (only func_other)
    temp_graph_manager.save_file_ast(
        file_a,
        [{"name": "func_other", "kind": "function", "line": 15}],
        [],
        [],
    )

    # Verify func_shared is NOT deleted because it is still defined in file B
    defs_after = temp_graph_manager.find_definition("func_shared")
    assert len(defs_after) == 1
    assert defs_after[0]["file_path"] == file_b

    res = temp_graph_manager._query("MATCH (s:Symbol {name: 'func_shared'}) RETURN s.name")
    rows = res[1] if len(res) > 1 and res[1] else []
    assert len(rows) == 1
    assert rows[0][0] == "func_shared"

    # Verify func_other exists
    defs_other = temp_graph_manager.find_definition("func_other")
    assert len(defs_other) == 1
    assert defs_other[0]["file_path"] == file_a


def test_delete_file_ast_removes_unresolved_reference_stubs(temp_graph_manager):
    """Deleting a file also removes stub Symbols it referenced that no other file defines or uses."""
    from tests.conftest import _SEATBELT_BLOCKED

    if _SEATBELT_BLOCKED:
        pytest.skip("regex FalkorDB emulator does not implement the orphan sweep")
    file_path = "src/caller.py"
    temp_graph_manager.save_file_ast(
        file_path,
        [{"name": "caller", "kind": "function", "line": 1}],
        [],
        [{"symbol": "external_helper", "line": 2, "caller": "caller"}],
    )
    res = temp_graph_manager._query("MATCH (s:Symbol {name: 'external_helper'}) RETURN s.name")
    assert len(res) > 1 and res[1], "stub should exist before deletion"

    temp_graph_manager.delete_file_ast(file_path)

    res = temp_graph_manager._query("MATCH (s:Symbol) RETURN s.name")
    assert not (len(res) > 1 and res[1])
