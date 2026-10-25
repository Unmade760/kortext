"""
Unit tests for FalkorDBClient parameter interpolation, regex safety, and connection lifecycle.
"""

import pytest
from kortext.falkordb_client import format_cypher_query, FalkorDBClient


class TestFalkorDBResilience:
    def test_parameter_interpolation_word_boundaries(self):
        """Verifies that $s does not corrupt $s_target or $status."""
        cypher = "MATCH (s:Symbol {name: $s}) WHERE s.target = $s_target AND s.status = $status RETURN s"
        params = {
            "s": "Foo",
            "s_target": "Bar",
            "status": "ready"
        }
        formatted = format_cypher_query(cypher, params)
        
        assert "name: 'Foo'" in formatted
        assert "s.target = 'Bar'" in formatted
        assert "s.status = 'ready'" in formatted
        # Ensure no accidental corrupted tokens like "'Foo'_target"
        assert "'Foo'_target" not in formatted

    def test_escaped_injection_sanitization(self):
        """Verifies that malicious string quotes do not break Cypher string literals."""
        cypher = "MATCH (e:Entity {name: $name}) RETURN e"
        params = {"name": "Robert'); DROP GRAPH kortext; --"}
        formatted = format_cypher_query(cypher, params)
        
        assert r"Robert\'); DROP GRAPH kortext; --" in formatted

    def test_null_and_boolean_formatting(self):
        cypher = "MERGE (t:Task {strict: $strict, error: $err})"
        params = {"strict": True, "err": None}
        formatted = format_cypher_query(cypher, params)
        
        assert "strict: true" in formatted
        assert "error: null" in formatted

    def test_dict_and_nested_structure_formatting(self):
        """Verifies that dicts and nested structures format recursively into Cypher maps and lists."""
        cypher = "CREATE (n:Node $props) SET n.meta = $meta"
        params = {
            "props": {"name": "TestNode", "count": 42, "is_active": True, "extra": None},
            "meta": {"nested": {"key": "val"}, "items": [1, "two", False]},
        }
        formatted = format_cypher_query(cypher, params)
        assert "name: 'TestNode'" in formatted
        assert "count: 42" in formatted
        assert "is_active: true" in formatted
        assert "extra: null" in formatted
        assert "nested: {key: 'val'}" in formatted
        assert "items: [1, 'two', false]" in formatted

    def test_list_of_dicts_formatting(self):
        """Verifies that lists of dicts format cleanly for UNWIND clauses."""
        cypher = "UNWIND $declarations AS d MERGE (s:Symbol {name: d.name})"
        params = {
            "declarations": [
                {"name": "foo", "line": 10},
                {"name": "bar", "line": 20},
            ]
        }
        formatted = format_cypher_query(cypher, params)
        assert "UNWIND [{name: 'foo', line: 10}, {name: 'bar', line: 20}] AS d" in formatted

    def test_build_cypher_params_header(self):
        """Verifies construction of native FalkorDB CYPHER headers."""
        from kortext.falkordb_client import build_cypher_params_header

        assert build_cypher_params_header(None) == ""
        assert build_cypher_params_header({}) == ""

        params = {"name": "Alice", "age": 30, "is_admin": False}
        header = build_cypher_params_header(params)
        assert header.startswith("CYPHER ")
        assert '`name`="Alice"' in header
        assert '`age`=30' in header
        assert '`is_admin`=False' in header

    def test_falkordb_client_query_parameter_binding(self):
        """Verifies that FalkorDBClient.query prepends native CYPHER parameter headers."""
        from unittest.mock import MagicMock
        client = FalkorDBClient()
        mock_redis = MagicMock()
        mock_redis.execute_command.return_value = [["res"]]
        client._r = mock_redis

        cypher = "MATCH (s:Symbol {name: $s}) RETURN s"
        params = {"s": "Foo"}
        res = client.query("test_graph", cypher, params)
        assert res == [["res"]]

        mock_redis.execute_command.assert_called_once()
        cmd, graph, executed_query = mock_redis.execute_command.call_args[0]
        assert cmd == "GRAPH.QUERY"
        assert graph == "test_graph"
        assert executed_query.startswith("CYPHER `s`=\"Foo\" ")
        assert "MATCH (s:Symbol {name: $s}) RETURN s" in executed_query

    def test_falkordb_client_query_preserves_existing_cypher_header(self):
        """Verifies that FalkorDBClient.query does not duplicate existing CYPHER header."""
        from unittest.mock import MagicMock
        client = FalkorDBClient()
        mock_redis = MagicMock()
        mock_redis.execute_command.return_value = [["res"]]
        client._r = mock_redis

        cypher = "CYPHER `s`=\"Foo\" MATCH (s:Symbol {name: $s}) RETURN s"
        params = {"s": "Bar"}
        client.query("test_graph", cypher, params)
        executed_query = mock_redis.execute_command.call_args[0][2]
        assert not executed_query.startswith("CYPHER CYPHER")

    def test_format_cypher_query_single_pass_safety(self):
        """Verifies that format_cypher_query does not perform recursive double substitution and ignores string literals."""
        cypher = "MATCH (s) WHERE s.note = 'Cost is $s' AND s.a = $a AND s.b = $b"
        params = {"a": "$b", "b": "safe", "s": "replaced"}
        formatted = format_cypher_query(cypher, params)
        # s.note string literal should be untouched
        assert "Cost is $s" in formatted
        # s.a should be '$b' and NOT double-substituted to 'safe'
        assert "s.a = '$b'" in formatted
        assert "s.b = 'safe'" in formatted


