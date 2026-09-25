"""
Unit tests for SymbolSeekEngine deterministic AST lookup.
"""

import json
import pytest
from unittest.mock import MagicMock
from cerebrum.symbols.seek import SymbolSeekEngine


class TestSymbolSeekEngine:
    @pytest.fixture
    def mock_seeker(self):
        seeker = SymbolSeekEngine()
        seeker.client = MagicMock()
        seeker.client.query.return_value = [
            ["symbol", "kind", "file", "line", "end_line", "signature", "docstring", "callers", "callees"],
            [
                [
                    "RetrievalEngine",
                    "class",
                    "cerebrum/retrieval/engine.py",
                    29,
                    186,
                    "class RetrievalEngine",
                    "Manages Qdrant index lifecycle and runs two-stage hybrid retrieval.",
                    [{"caller": "main", "file": "cerebrum/server.py", "line": 88}],
                    [{"callee": "query_points", "file": "qdrant_client"}]
                ]
            ]
        ]
        return seeker

    def test_seek_symbol_exact_match(self, mock_seeker):
        res_json = mock_seeker.seek_symbol("RetrievalEngine")
        data = json.loads(res_json)

        assert data["status"] == "found"
        assert len(data["matches"]) == 1
        match = data["matches"][0]
        assert match["symbol"] == "RetrievalEngine"
        assert match["lines"] == [29, 186]
        assert len(match["callers"]) == 1
        assert match["callers"][0]["caller"] == "main"

    def test_seek_symbol_not_found(self):
        seeker = SymbolSeekEngine()
        seeker.client = MagicMock()
        seeker.client.query.return_value = [[], []]

        res_json = seeker.seek_symbol("NonExistentClass")
        data = json.loads(res_json)
        assert data["status"] == "not_found"
