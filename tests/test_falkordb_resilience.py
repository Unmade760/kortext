"""
Unit tests for FalkorDBClient parameter interpolation, regex safety, and connection lifecycle.
"""

import pytest
from cerebrum.falkordb_client import format_cypher_query, FalkorDBClient


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
        params = {"name": "Robert'); DROP GRAPH cerebrum; --"}
        formatted = format_cypher_query(cypher, params)
        
        assert r"Robert\'); DROP GRAPH cerebrum; --" in formatted

    def test_null_and_boolean_formatting(self):
        cypher = "MERGE (t:Task {strict: $strict, error: $err})"
        params = {"strict": True, "err": None}
        formatted = format_cypher_query(cypher, params)
        
        assert "strict: true" in formatted
        assert "error: null" in formatted
