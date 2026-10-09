"""
Unit tests for FalkorDB client consolidation and lazy index creation.
Verifies task_e14841ec and task_e9d7f4a7.
"""

from unittest.mock import MagicMock, patch
import pytest

from kortext.falkordb_client import FalkorDBClient, get_shared_falkordb_client
from kortext.symbols.graph import SymbolGraphManager
from kortext.invariants import InvariantGroundingEngine
from kortext.dream import DreamEngine
from kortext.symbols.scip import SCIPImporter


class TestFalkorDBClientConsolidation:
    def test_symbol_graph_manager_client_injection(self):
        custom_client = MagicMock(spec=FalkorDBClient)
        sgm = SymbolGraphManager(client=custom_client)
        assert sgm.client is custom_client

    def test_symbol_graph_manager_default_client(self):
        sgm = SymbolGraphManager()
        assert sgm.client is get_shared_falkordb_client()

    def test_invariant_grounding_engine_client_injection(self):
        custom_client = MagicMock(spec=FalkorDBClient)
        ige = InvariantGroundingEngine(client=custom_client)
        assert ige.client is custom_client

    def test_invariant_grounding_engine_default_client(self):
        ige = InvariantGroundingEngine()
        assert ige.client is get_shared_falkordb_client()

    def test_dream_engine_client_injection(self):
        custom_client = MagicMock(spec=FalkorDBClient)
        de = DreamEngine(client=custom_client)
        assert de.client is custom_client
        assert de.invariant_engine.client is custom_client

    def test_dream_engine_default_client(self):
        de = DreamEngine()
        assert de.client is get_shared_falkordb_client()
        assert de.invariant_engine.client is get_shared_falkordb_client()

    def test_scip_importer_client_injection(self):
        custom_client = MagicMock(spec=FalkorDBClient)
        importer = SCIPImporter(client=custom_client)
        assert importer.client is custom_client

    def test_scip_importer_default_client(self):
        importer = SCIPImporter()
        assert importer.client is get_shared_falkordb_client()


class TestLazyIndexEnsured:
    def test_symbol_graph_manager_lazy_index_called_once(self):
        mock_client = MagicMock(spec=FalkorDBClient)
        mock_client.query.return_value = [["res"], [["ok"]]]
        sgm = SymbolGraphManager(client=mock_client)

        with patch.object(sgm, "_ensure_indexes", wraps=sgm._ensure_indexes) as mock_ensure:
            # First query should trigger _ensure_indexes
            sgm._query("RETURN 1")
            assert mock_ensure.call_count == 1
            assert sgm._indexes_ensured is True

            # Subsequent queries should NOT call _ensure_indexes again
            sgm._query("RETURN 2")
            sgm._query("RETURN 3")
            assert mock_ensure.call_count == 1

    def test_scip_importer_lazy_index_called_once(self):
        mock_client = MagicMock(spec=FalkorDBClient)
        mock_client.query.return_value = [["res"], [["ok"]]]
        importer = SCIPImporter(client=mock_client)

        with patch.object(importer, "_ensure_indexes", wraps=importer._ensure_indexes) as mock_ensure:
            # First query should trigger _ensure_indexes
            importer._query("RETURN 1")
            assert mock_ensure.call_count == 1
            assert importer._indexes_ensured is True

            # Subsequent queries should NOT call _ensure_indexes again
            importer._query("RETURN 2")
            importer._query("RETURN 3")
            assert mock_ensure.call_count == 1


class TestSymbolGraphAstParameterization:
    def test_save_file_ast_parameterized(self):
        mock_client = MagicMock(spec=FalkorDBClient)
        mock_client.query.return_value = [["res"], [["ok"]]]
        sgm = SymbolGraphManager(client=mock_client)

        sgm.save_file_ast(
            file_path="src/app.py",
            declarations=[{
                "name": "UserHandler",
                "kind": "class",
                "line": 10,
                "end_line": 50,
                "signature": "class UserHandler:",
                "docstring": "Handles user requests.",
                "parent": ""
            }],
            imports=[{
                "symbol": "BaseHandler",
                "module": "base",
                "line": 2
            }],
            references=[{
                "symbol": "json_loads",
                "kind": "call",
                "line": 15,
                "caller": "UserHandler"
            }]
        )

        queries = [call[0][1] for call in mock_client.query.call_args_list]
        params_list = [call[0][2] for call in mock_client.query.call_args_list]

        # Check candidate symbol lookup queries
        assert "DEFINED_IN" in queries[0]
        assert params_list[0] == {"path": "src/app.py"}
        assert "file_path: $path" in queries[1]
        assert params_list[1] == {"path": "src/app.py"}

        # Check purge query
        assert "$path" in queries[2]
        assert params_list[2] == {"path": "src/app.py"}

        # Check declarations query
        assert "$declarations" in queries[3]
        assert params_list[3]["path"] == "src/app.py"
        assert len(params_list[3]["declarations"]) == 1
        assert params_list[3]["declarations"][0]["name"] == "UserHandler"

        # Check imports query
        assert "$imports" in queries[4]
        assert params_list[4]["path"] == "src/app.py"
        assert len(params_list[4]["imports"]) == 1
        assert params_list[4]["imports"][0]["name"] == "BaseHandler"

        # Check references query
        assert "$references" in queries[5]
        assert params_list[5]["path"] == "src/app.py"
        assert len(params_list[5]["references"]) == 1
        assert params_list[5]["references"][0]["name"] == "json_loads"

        # Check orphan sweep query
        assert "$names" in queries[6]
        assert params_list[6]["names"] == ["ok"]

    def test_save_markdown_ast_parameterized(self):
        mock_client = MagicMock(spec=FalkorDBClient)
        mock_client.query.return_value = [["res"], [["ok"]]]
        sgm = SymbolGraphManager(client=mock_client)

        sgm.save_markdown_ast(
            file_path="docs/arch.md",
            title="Architecture",
            frontmatter={},
            sections=[{
                "id": "intro",
                "name": "Introduction",
                "level": 1,
                "line": 1,
                "heading_path": "Introduction"
            }],
            declarations=[{
                "name": "Introduction",
                "kind": "section",
                "line": 1,
                "signature": "# Introduction",
                "docstring": "",
                "parent": ""
            }],
            links=[
                {"is_resolved": True, "target_path": "docs/design.md", "label": "Design", "line": 5, "link_type": "markdown_link", "raw_target": "./design.md"},
                {"is_resolved": False, "target_name": "CachingConcept", "label": "Caching", "line": 10, "link_type": "wiki_link", "raw_target": "[[CachingConcept]]"}
            ],
            tags=["architecture", "spec"]
        )

        queries = [call[0][1] for call in mock_client.query.call_args_list]
        params_list = [call[0][2] for call in mock_client.query.call_args_list]

        # 1. Purge & Title
        assert "$title" in queries[0]
        assert params_list[0]["title"] == "Architecture"

        # 2. Sections
        assert "$sections" in queries[1]
        assert len(params_list[1]["sections"]) == 1
        assert params_list[1]["sections"][0]["id"] == "intro"

        # 3. Declarations
        assert "$declarations" in queries[2]
        assert len(params_list[2]["declarations"]) == 1
        assert params_list[2]["declarations"][0]["name"] == "Introduction"

        # 4. Resolved links
        assert "$links" in queries[3]
        assert len(params_list[3]["links"]) == 1
        assert params_list[3]["links"][0]["path"] == "docs/design.md"

        # 5. Concept links
        assert "$links" in queries[4]
        assert len(params_list[4]["links"]) == 1
        assert params_list[4]["links"][0]["name"] == "CachingConcept"

        # 6. Tags
        assert "$tags" in queries[5]
        assert len(params_list[5]["tags"]) == 2
        assert params_list[5]["tags"][0]["name"] == "architecture"
