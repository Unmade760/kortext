"""
Unit tests for SymbolSeekEngine deterministic AST lookup.
"""

import json
import pytest
from unittest.mock import ANY, MagicMock, patch
from kortext.symbols.seek import SymbolSeekEngine


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
                    "kortext/retrieval/engine.py",
                    29,
                    186,
                    "class RetrievalEngine",
                    "Manages Qdrant index lifecycle and runs two-stage hybrid retrieval.",
                    [{"caller": "main", "file": "kortext/server.py", "line": 88}],
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

    def test_seek_symbol_with_prose_query(self):
        seeker = SymbolSeekEngine()
        seeker.client = MagicMock()

        def mock_query(graph, cypher, params=None, read_only=False):
            if params and params.get("name") == "TokenOptimizer":
                return [
                    ["symbol", "kind", "file", "line", "end_line", "signature", "docstring", "callers", "callees"],
                    [
                        [
                            "TokenOptimizer",
                            "class",
                            "kortext/llm/optimizer.py",
                            10,
                            50,
                            "class TokenOptimizer",
                            "Optimizes prompt tokens.",
                            [],
                            []
                        ]
                    ]
                ]
            return [[], []]

        seeker.client.query.side_effect = mock_query
        res_json = seeker.seek_symbol("how does token optimizer work?")
        data = json.loads(res_json)
        assert data["status"] == "found"
        assert len(data["matches"]) == 1
        assert data["matches"][0]["symbol"] == "TokenOptimizer"


class TestExtractSymbolCandidates:
    def test_extract_pascal_case(self):
        from kortext.symbols.seek import extract_symbol_candidates
        query = "Where is RetrievalEngine and SymbolSeekEngine defined? Also check ASTCodeSplitter."
        cands = extract_symbol_candidates(query)
        assert "RetrievalEngine" in cands
        assert "SymbolSeekEngine" in cands
        assert "ASTCodeSplitter" in cands

    def test_extract_camel_case(self):
        from kortext.symbols.seek import extract_symbol_candidates
        query = "How does extractSymbolCandidates and getElementById work?"
        cands = extract_symbol_candidates(query)
        assert "extractSymbolCandidates" in cands
        assert "getElementById" in cands

    def test_extract_snake_case_and_constants(self):
        from kortext.symbols.seek import extract_symbol_candidates
        query = "Verify _extract_symbol_candidates and MAX_BUFFER_SIZE handling"
        cands = extract_symbol_candidates(query)
        assert "_extract_symbol_candidates" in cands
        assert "MAX_BUFFER_SIZE" in cands

    def test_extract_dotted_identifiers(self):
        from kortext.symbols.seek import extract_symbol_candidates
        query = "Check kortext.symbols.seek and engine._extract_symbol_candidates"
        cands = extract_symbol_candidates(query)
        assert "kortext.symbols.seek" in cands
        assert "engine._extract_symbol_candidates" in cands

    def test_extract_backticks_and_intents(self):
        from kortext.symbols.seek import extract_symbol_candidates
        query = "Find `CustomType` and definition of MyService"
        cands = extract_symbol_candidates(query)
        assert "CustomType" in cands
        assert "MyService" in cands

    def test_no_false_positives_on_english_stop_words(self):
        from kortext.symbols.seek import extract_symbol_candidates
        query = "What does this file do and how can we test it?"
        cands = extract_symbol_candidates(query)
        assert cands == []

        title_case_query = "Just Some Normal English Text With Capitalized Words That Should Not Match"
        title_cands = extract_symbol_candidates(title_case_query)
        assert title_cands == []

    def test_max_candidates_limit(self):
        from kortext.symbols.seek import extract_symbol_candidates
        query = "AlphaBeta GammaDelta EpsilonZeta EtaTheta IotaKappa LambdaMu"
        cands = extract_symbol_candidates(query, max_candidates=3)
        assert len(cands) == 3

    def test_prose_query_fallback(self):
        from kortext.symbols.seek import extract_symbol_candidates
        # Weakness 2.4: prose questions without snake_case/camelCase
        cands = extract_symbol_candidates("how does token optimizer work?")
        assert "token_optimizer" in cands
        assert "TokenOptimizer" in cands

        # Other prose queries
        cands_retrieval = extract_symbol_candidates("where is retrieval engine defined?")
        assert "retrieval_engine" in cands_retrieval
        assert "RetrievalEngine" in cands_retrieval

        cands_sanitizer = extract_symbol_candidates("what does causal sanitizer do?")
        assert "causal_sanitizer" in cands_sanitizer
        assert "CausalSanitizer" in cands_sanitizer

        cands_seek = extract_symbol_candidates("how does symbol seek engine work?")
        assert "symbol_seek_engine" in cands_seek
        assert "SymbolSeekEngine" in cands_seek

    def test_sole_custodian_dense_vector_fallback_never_instantiates_embedded_qdrant(self, monkeypatch):
        from kortext.symbols.seek import extract_symbol_candidates

        # If EmbeddedQdrantEngine were instantiated, raise an error
        mock_init = MagicMock(side_effect=AssertionError("EmbeddedQdrantEngine must never be instantiated directly!"))
        monkeypatch.setattr("kortext.retrieval.qdrant_engine.EmbeddedQdrantEngine.__init__", mock_init)

        # Query consisting only of stop words produces no regex candidates
        cands = extract_symbol_candidates("what does it do", qdrant_engine=None)
        assert cands == []
        mock_init.assert_not_called()

    def test_sole_custodian_uses_injected_qdrant_engine_with_kortext_codebase(self):
        from kortext.symbols.seek import extract_symbol_candidates

        mock_engine = MagicMock()
        mock_engine.client.collection_exists.return_value = True
        mock_point = MagicMock()
        mock_point.payload = {"defined_symbols": ["CustomInjectedSymbol"]}
        mock_resp = MagicMock()
        mock_resp.points = [mock_point]
        mock_engine.client.query_points.return_value = mock_resp

        cands = extract_symbol_candidates("what does it do", qdrant_engine=mock_engine)
        assert "CustomInjectedSymbol" in cands
        mock_engine.client.query_points.assert_called_once_with(
            collection_name="kortext_codebase", query=ANY, using="text-dense", limit=2
        )

    def test_sole_custodian_fallback_to_codebase_alias_when_default_absent(self):
        from kortext.symbols.seek import extract_symbol_candidates

        mock_engine = MagicMock()
        mock_engine.client.collection_exists.side_effect = lambda name: name == "codebase"
        mock_point = MagicMock()
        mock_point.payload = {"symbols": ["LegacyAliasSymbol"]}
        mock_resp = MagicMock()
        mock_resp.points = [mock_point]
        mock_engine.client.query_points.return_value = mock_resp

        cands = extract_symbol_candidates("what does it do", qdrant_engine=mock_engine)
        assert "LegacyAliasSymbol" in cands
        mock_engine.client.query_points.assert_called_once_with(
            collection_name="codebase", query=ANY, using="text-dense", limit=2
        )

    def test_symbol_seek_engine_accepts_and_passes_qdrant_engine(self):
        mock_engine = MagicMock()
        seeker = SymbolSeekEngine(qdrant_engine=mock_engine)
        assert seeker.qdrant_engine is mock_engine


class TestFormatImpactReport:
    def test_format_impact_report_basic(self):
        from kortext.symbols.formatter import format_impact_report

        definitions = [
            {"name": "MyEngine", "kind": "class", "file_path": "kortext/engine.py", "line": 10, "signature": "class MyEngine"}
        ]
        direct_impacts = [
            {"source_file": "kortext/app.py", "relation": "IMPORTS", "line": 5, "target_symbol": "MyEngine"}
        ]
        type_hierarchies = [
            {"symbol": "BaseEngine", "relation": "IMPLEMENTS", "file_path": "kortext/base.py"}
        ]
        transitive_impacts = [
            {"source_file": "kortext/main.py", "depth": 2, "symbol": "MyEngine", "relation": "TRANSITIVE_CALLER"}
        ]

        report = format_impact_report(
            clean_name="MyEngine",
            direction="upstream",
            depth=2,
            definitions=definitions,
            direct_impacts=direct_impacts,
            type_hierarchies=type_hierarchies,
            transitive_impacts=transitive_impacts,
            token_budget=1500,
        )

        assert report["symbol"] == "MyEngine"
        assert report["direction"] == "upstream"
        assert report["max_depth"] == 2
        assert report["total_impacted_locations"] == 3
        assert report["budget_exceeded"] is False
        assert report["detail_levels_applied"]["l1_full"] == 2  # direct + hierarchy
        assert report["detail_levels_applied"]["l0_compact"] == 1  # transitive
        assert report["detail_levels_applied"]["aggregated_count"] == 0
        assert "Symbol blast radius: `MyEngine`" in report["formatted_summary"]
        assert "kortext/app.py:5" in report["formatted_summary"]

    def test_format_impact_report_budget_overflow(self):
        from kortext.symbols.formatter import format_impact_report

        definitions = [
            {"name": "PopularFunc", "kind": "function", "file_path": "kortext/core.py", "line": 42}
        ]
        direct_impacts = [
            {"source_file": f"kortext/module_{i}.py", "relation": "CALLS", "line": i * 10, "target_symbol": "PopularFunc"}
            for i in range(50)
        ]

        report = format_impact_report(
            clean_name="PopularFunc",
            direction="upstream",
            depth=1,
            definitions=definitions,
            direct_impacts=direct_impacts,
            type_hierarchies=[],
            transitive_impacts=[],
            token_budget=50,  # Small budget to force Knapsack degradation
        )

        assert report["budget_exceeded"] is True
        assert report["detail_levels_applied"]["aggregated_count"] > 0
        assert "omitted to fit token budget" in report["formatted_summary"]

    def test_trace_symbol_impact_delegation(self):
        from kortext.symbols.graph import SymbolGraphManager

        mgr = SymbolGraphManager.__new__(SymbolGraphManager)
        mgr.find_definition = MagicMock(return_value=[
            {"name": "target_fn", "kind": "function", "file_path": "a.py", "line": 1, "signature": "def target_fn()"}
        ])
        mgr._query = MagicMock(side_effect=[
            # 1. direct
            ["hdr", [["caller.py", "REFERENCES", 12]]],
            # 2. backlinks
            ["hdr", []],
            # 3. type relations
            ["hdr", []],
            # 4. multi-hop
            ["hdr", []],
        ])

        report = mgr.trace_symbol_impact("target_fn", direction="upstream", max_depth=1)
        assert report["symbol"] == "target_fn"
        assert report["definitions"][0]["name"] == "target_fn"
        assert len(report["direct_impacts"]) == 1
        assert report["direct_impacts"][0]["source_file"] == "caller.py"
        assert "caller.py:12" in report["formatted_summary"]

    def test_symbol_seek_engine_trace_impact_delegation(self):
        seeker = SymbolSeekEngine()
        mock_graph_mgr = MagicMock()
        mock_graph_mgr.trace_symbol_impact.return_value = {
            "symbol": "MyClass",
            "direction": "upstream",
            "max_depth": 2,
            "detail_level": "skeleton",
            "definitions": [],
            "direct_impacts": [{"source_file": "app.py", "line": 10, "relation": "CALLS", "target_symbol": "MyClass"}],
            "type_hierarchies": [],
            "transitive_impacts": [],
            "total_impacted_locations": 1,
            "token_budget": 1500,
            "effective_tokens": 50,
            "budget_exceeded": False,
            "detail_levels_applied": {"l1_full": 1, "l0_compact": 0, "aggregated_count": 0},
            "formatted_summary": "### Symbol blast radius: `MyClass`",
        }
        seeker.graph_manager = mock_graph_mgr

        raw_res = seeker.trace_impact("MyClass", depth=2)
        assert isinstance(raw_res, str)
        data = json.loads(raw_res)
        assert data["symbol"] == "MyClass"
        assert "formatted_summary" in data
        assert "direct_impacts" in data
        mock_graph_mgr.trace_symbol_impact.assert_called_once_with(
            symbol_name="MyClass",
            direction="upstream",
            max_depth=2,
            token_budget=1500,
        )

    def test_symbol_seek_engine_trace_impact_direction_and_budget(self):
        seeker = SymbolSeekEngine()
        mock_graph_mgr = MagicMock()
        mock_graph_mgr.trace_symbol_impact.return_value = {
            "symbol": "MyClass",
            "direction": "downstream",
            "max_depth": 4,
            "formatted_summary": "downstream summary",
        }
        seeker.graph_manager = mock_graph_mgr

        raw_res = seeker.trace_impact("MyClass", depth=4, direction="downstream", token_budget=800)
        data = json.loads(raw_res)
        assert data["direction"] == "downstream"
        mock_graph_mgr.trace_symbol_impact.assert_called_once_with(
            symbol_name="MyClass",
            direction="downstream",
            max_depth=4,
            token_budget=800,
        )

    def test_symbol_seek_engine_trace_impact_instantiates_graph_manager_if_none(self):
        with patch("kortext.symbols.graph.SymbolGraphManager") as mock_mgr_cls:
            mock_mgr_instance = MagicMock()
            mock_mgr_instance.trace_symbol_impact.return_value = {
                "symbol": "TargetSymbol",
                "formatted_summary": "Summary",
            }
            mock_mgr_cls.return_value = mock_mgr_instance

            seeker = SymbolSeekEngine()
            seeker.trace_impact("TargetSymbol", depth=3)

            mock_mgr_cls.assert_called_once_with(client=seeker.client)
            mock_mgr_instance.trace_symbol_impact.assert_called_once_with(
                symbol_name="TargetSymbol",
                direction="upstream",
                max_depth=3,
                token_budget=1500,
            )


class TestDenseVectorFallback:
    def test_dense_vector_fallback_when_regex_and_keyword_empty(self):
        from kortext.symbols.seek import extract_symbol_candidates

        mock_engine = MagicMock()
        mock_point = MagicMock()
        mock_point.payload = {"defined_symbols": ["VectorFallbackClass"]}
        mock_engine.client.query_points.return_value = MagicMock(points=[mock_point])

        # Query with punctuation/stopwords that yields empty candidates from regex/keywords
        cands = extract_symbol_candidates("??!", qdrant_engine=mock_engine)
        assert "VectorFallbackClass" in cands

    def test_dense_vector_fallback_extracts_defined_symbols_symbols_and_name(self):
        from kortext.symbols.seek import extract_symbol_candidates

        mock_engine = MagicMock()
        p1 = MagicMock()
        p1.payload = {"defined_symbols": ["AlphaSymbol"], "name": "BetaSymbol"}
        p2 = MagicMock()
        p2.payload = {"metadata": {"symbols": ["GammaSymbol"]}}
        mock_engine.client.query_points.return_value = MagicMock(points=[p1, p2])

        cands = extract_symbol_candidates("??!", qdrant_engine=mock_engine)
        assert "AlphaSymbol" in cands
        assert "BetaSymbol" in cands
        assert "GammaSymbol" in cands


class TestSymbolSeekEngineLRUCache:
    def test_lru_cache_hit_and_speed(self, tmp_path):
        import time
        from kortext.symbols.seek import SymbolSeekEngine

        dummy_file = tmp_path / "service.py"
        dummy_file.write_text("class CachedService:\n    pass\n")

        seeker = SymbolSeekEngine()
        seeker.client = MagicMock()
        seeker.client.query.return_value = [
            ["symbol", "kind", "file", "line", "end_line", "signature", "docstring", "callers", "callees"],
            [
                [
                    "CachedService",
                    "class",
                    str(dummy_file),
                    1,
                    2,
                    "class CachedService",
                    "Cached doc",
                    [],
                    [],
                ]
            ],
        ]

        # 1. First lookup: Populates cache
        res1 = seeker.seek_symbol("CachedService")
        data1 = json.loads(res1)
        assert data1["status"] == "found"
        assert seeker.client.query.call_count == 1

        # Check internal cache
        mtime = dummy_file.stat().st_mtime
        assert ("CachedService", mtime) in seeker._cache

        # 2. Second lookup: Cache HIT, <0.05ms, no new query call
        t0 = time.perf_counter()
        res2 = seeker.seek_symbol("CachedService")
        t_elapsed_ms = (time.perf_counter() - t0) * 1000.0

        assert res1 == res2
        assert seeker.client.query.call_count == 1  # Did not query client again
        assert t_elapsed_ms < 1.0  # Well within <0.05ms, asserting <1ms in CI

    def test_lru_cache_invalidation_on_file_mtime_change(self, tmp_path):
        import os
        from kortext.symbols.seek import SymbolSeekEngine

        dummy_file = tmp_path / "service.py"
        dummy_file.write_text("class ChangingService:\n    pass\n")

        seeker = SymbolSeekEngine()
        seeker.client = MagicMock()
        seeker.client.query.return_value = [
            ["symbol", "kind", "file", "line", "end_line", "signature", "docstring", "callers", "callees"],
            [
                [
                    "ChangingService",
                    "class",
                    str(dummy_file),
                    1,
                    2,
                    "class ChangingService",
                    "Doc",
                    [],
                    [],
                ]
            ],
        ]

        seeker.seek_symbol("ChangingService")
        assert seeker.client.query.call_count == 1

        # Simulate file modification (advance mtime)
        new_mtime = dummy_file.stat().st_mtime + 10.0
        os.utime(dummy_file, (new_mtime, new_mtime))

        # Lookup again should detect mtime change and query FalkorDB
        seeker.seek_symbol("ChangingService")
        assert seeker.client.query.call_count == 2


class TestBidirectionalASTScopeAffinity:
    def test_scope_affinity_boost_companion_and_callees_callers(self):
        from kortext.symbols.graph import SymbolGraphManager

        mgr = SymbolGraphManager.__new__(SymbolGraphManager)
        # Mock get_companion_symbols and get_hop_symbols
        mgr.get_companion_symbols = MagicMock(return_value=["HelperService"])
        mgr.get_hop_symbols = MagicMock(return_value=["DependencyClient"])

        candidates = [
            {"symbol": "RootService", "score": 0.90},
            {"symbol": "HelperService", "score": 0.60},
            {"symbol": "DependencyClient", "score": 0.50},
            {"symbol": "UnrelatedService", "score": 0.40},
        ]

        ranked = mgr.apply_scope_affinity(candidates)

        score_map = {item["symbol"]: item["score"] for item in ranked}
        assert score_map["RootService"] == 0.90
        # HelperService: companion defined in same file boosted by +0.15 (0.60 + 0.15 = 0.75)
        assert round(score_map["HelperService"], 2) == 0.75
        # DependencyClient: direct 1-hop callee/caller boosted by +0.10 (0.50 + 0.10 = 0.60)
        assert round(score_map["DependencyClient"], 2) == 0.60
        # UnrelatedService: unchanged
        assert score_map["UnrelatedService"] == 0.40

    def test_scope_affinity_no_boost_when_confidence_low(self):
        from kortext.symbols.graph import SymbolGraphManager

        mgr = SymbolGraphManager.__new__(SymbolGraphManager)
        mgr.get_companion_symbols = MagicMock(return_value=["HelperService"])
        mgr.get_hop_symbols = MagicMock(return_value=["DependencyClient"])

        # Rank-1 symbol score is 0.80 (<= 0.85), so no boost
        candidates = [
            {"symbol": "RootService", "score": 0.80},
            {"symbol": "HelperService", "score": 0.60},
        ]

        ranked = mgr.apply_scope_affinity(candidates)
        score_map = {item["symbol"]: item["score"] for item in ranked}
        assert score_map["RootService"] == 0.80
        assert score_map["HelperService"] == 0.60

    def test_scope_affinity_dual_boost(self):
        from kortext.symbols.graph import SymbolGraphManager

        mgr = SymbolGraphManager.__new__(SymbolGraphManager)
        # DualService is BOTH companion in same file and 1-hop caller/callee
        mgr.get_companion_symbols = MagicMock(return_value=["DualService"])
        mgr.get_hop_symbols = MagicMock(return_value=["DualService"])

        candidates = [
            {"symbol": "RootService", "score": 0.92},
            {"symbol": "DualService", "score": 0.50},
        ]

        ranked = mgr.apply_scope_affinity(candidates)
        score_map = {item["symbol"]: item["score"] for item in ranked}
        # Boost is +0.15 + 0.10 = +0.25 -> 0.50 + 0.25 = 0.75
        assert round(score_map["DualService"], 2) == 0.75


class TestProgressiveASTDetailLevels:
    @pytest.fixture
    def sample_code_file(self, tmp_path):
        code_file = tmp_path / "calculator.py"
        code = '''"""Calculator module docstring."""

class Calculator:
    """A sample calculator class."""
    precision: int = 4
    mode: str

    def __init__(self, precision: int = 4) -> None:
        """Initialize calculator."""
        self.precision = precision
        self.history = []

    def add(self, a: float, b: float) -> float:
        """Add two numbers."""
        res = a + b
        self.history.append(("add", a, b, res))
        return round(res, self.precision)

    def multiply(self, a: float, b: float) -> float:
        """Multiply two numbers."""
        res = a * b
        self.history.append(("multiply", a, b, res))
        return round(res, self.precision)


def standalone_compute(x: int) -> int:
    """Compute square of number."""
    val = x * x
    return val
'''
        code_file.write_text(code)
        return code_file

    def test_seek_symbol_skeleton_default(self, sample_code_file):
        seeker = SymbolSeekEngine()
        seeker.client = MagicMock()
        seeker.client.query.return_value = [
            ["symbol", "kind", "file", "line", "end_line", "signature", "docstring", "callers", "callees"],
            [
                [
                    "Calculator",
                    "class",
                    str(sample_code_file),
                    3,
                    24,
                    "class Calculator",
                    "A sample calculator class.",
                    [{"caller": "main", "file": "app.py", "line": 10}],
                    [{"callee": "round", "file": "builtins"}]
                ]
            ]
        ]

        res_json = seeker.seek_symbol("Calculator")
        data = json.loads(res_json)

        assert data["status"] == "found"
        assert len(data["matches"]) == 1
        m = data["matches"][0]
        assert m["detail_level"] == "skeleton"
        assert "class Calculator" in m["code"]
        assert "A sample calculator class." in m["code"]
        assert "..." in m["code"]
        # In skeleton mode, inner implementation logic must be trimmed
        assert "self.history.append" not in m["code"]
        assert "round(res, self.precision)" not in m["code"]
        # Callers and callees preserved for graph navigation
        assert len(m["callers"]) == 1

    def test_seek_symbol_interface_level(self, sample_code_file):
        seeker = SymbolSeekEngine()
        seeker.client = MagicMock()
        seeker.client.query.return_value = [
            ["symbol", "kind", "file", "line", "end_line", "signature", "docstring", "callers", "callees"],
            [
                [
                    "Calculator",
                    "class",
                    str(sample_code_file),
                    3,
                    24,
                    "class Calculator",
                    "A sample calculator class.",
                    [{"caller": "main", "file": "app.py", "line": 10}],
                    [{"callee": "round", "file": "builtins"}]
                ]
            ]
        ]

        res_json = seeker.seek_symbol("Calculator", detail_level="interface")
        data = json.loads(res_json)

        assert data["status"] == "found"
        m = data["matches"][0]
        assert m["detail_level"] == "interface"
        # Interface includes method signatures
        assert "def add" in m["code"]
        assert "def multiply" in m["code"]
        assert "..." in m["code"]
        # Implementation details omitted
        assert "self.history.append" not in m["code"]
        # Methods list provided
        assert any("add" in meth for meth in m["methods"])
        assert any("multiply" in meth for meth in m["methods"])

    def test_seek_symbol_full_level(self, sample_code_file):
        seeker = SymbolSeekEngine()
        seeker.client = MagicMock()
        seeker.client.query.return_value = [
            ["symbol", "kind", "file", "line", "end_line", "signature", "docstring", "callers", "callees"],
            [
                [
                    "Calculator",
                    "class",
                    str(sample_code_file),
                    3,
                    24,
                    "class Calculator",
                    "A sample calculator class.",
                    [],
                    []
                ]
            ]
        ]

        res_json = seeker.seek_symbol("Calculator", detail_level="full")
        data = json.loads(res_json)

        assert data["status"] == "found"
        m = data["matches"][0]
        assert m["detail_level"] == "full"
        # Full mode contains unabridged code
        assert "self.history.append((\"add\", a, b, res))" in m["code"]
        assert "self.history.append((\"multiply\", a, b, res))" in m["code"]

    def test_seek_symbol_function_skeleton(self, sample_code_file):
        seeker = SymbolSeekEngine()
        seeker.client = MagicMock()
        seeker.client.query.return_value = [
            ["symbol", "kind", "file", "line", "end_line", "signature", "docstring", "callers", "callees"],
            [
                [
                    "standalone_compute",
                    "function",
                    str(sample_code_file),
                    27,
                    30,
                    "def standalone_compute(x: int) -> int",
                    "Compute square of number.",
                    [],
                    []
                ]
            ]
        ]

        res_json = seeker.seek_symbol("standalone_compute", detail_level="skeleton")
        data = json.loads(res_json)

        m = data["matches"][0]
        assert "def standalone_compute" in m["code"]
        assert "Compute square of number." in m["code"]
        assert "..." in m["code"]
        assert "val = x * x" not in m["code"]

    def test_seek_symbol_file_not_found_fallback(self):
        seeker = SymbolSeekEngine()
        seeker.client = MagicMock()
        seeker.client.query.return_value = [
            ["symbol", "kind", "file", "line", "end_line", "signature", "docstring", "callers", "callees"],
            [
                [
                    "VirtualClass",
                    "class",
                    "non_existent/path/virtual.py",
                    1,
                    10,
                    "class VirtualClass",
                    "Virtual docstring.",
                    [],
                    []
                ]
            ]
        ]

        res_skeleton = json.loads(seeker.seek_symbol("VirtualClass", detail_level="skeleton"))
        m_skel = res_skeleton["matches"][0]
        assert "class VirtualClass" in m_skel["code"]
        assert "Virtual docstring." in m_skel["code"]
        assert "..." in m_skel["code"]

        res_full = json.loads(seeker.seek_symbol("VirtualClass", detail_level="full"))
        m_full = res_full["matches"][0]
        assert "class VirtualClass" in m_full["code"]
        assert "Virtual docstring." in m_full["code"]

    def test_format_impact_report_respects_detail_level(self):
        from kortext.symbols.formatter import format_impact_report

        definitions = [
            {
                "name": "MyEngine",
                "kind": "class",
                "file_path": "kortext/engine.py",
                "line": 10,
                "signature": "class MyEngine",
                "docstring": "Core engine docstring.",
                "code": "class MyEngine:\n    def run(self): return True",
            }
        ]

        report_full = format_impact_report(
            clean_name="MyEngine",
            direction="upstream",
            depth=1,
            definitions=definitions,
            direct_impacts=[],
            type_hierarchies=[],
            transitive_impacts=[],
            detail_level="full",
        )
        assert report_full["detail_level"] == "full"
        assert "class MyEngine:\n    def run(self): return True" in report_full["formatted_summary"]

        report_skel = format_impact_report(
            clean_name="MyEngine",
            direction="upstream",
            depth=1,
            definitions=definitions,
            direct_impacts=[],
            type_hierarchies=[],
            transitive_impacts=[],
            detail_level="skeleton",
        )
        assert report_skel["detail_level"] == "skeleton"
        assert "Core engine docstring." in report_skel["formatted_summary"]

    def test_extract_symbol_source_detail_non_python_syntax(self, tmp_path):
        from kortext.symbols.seek import extract_symbol_source_detail

        # 1. TypeScript file with syntax that would fail python ast.parse
        ts_file = tmp_path / "service.ts"
        ts_code = (
            "export class AuthService {\n"
            "    private token: string;\n"
            "    constructor(token: string) {\n"
            "        this.token = token;\n"
            "    }\n"
            "    async authenticate(): Promise<boolean> {\n"
            "        return this.token.length > 0;\n"
            "    }\n"
            "}\n"
        )
        ts_file.write_text(ts_code)

        detail = extract_symbol_source_detail(
            file_path=str(ts_file),
            line=1,
            end_line=9,
            kind="class",
            signature="export class AuthService",
            docstring="Authentication service in TypeScript.",
            callers=[],
            callees=[],
            detail_level="skeleton",
        )
        assert detail["detail_level"] == "skeleton"
        assert "export class AuthService" in detail["code"]
        assert "..." in detail["code"]

        # Full detail returns unabridged TS code
        detail_full = extract_symbol_source_detail(
            file_path=str(ts_file),
            line=1,
            end_line=9,
            kind="class",
            signature="export class AuthService",
            docstring="Authentication service in TypeScript.",
            callers=[],
            callees=[],
            detail_level="full",
        )
        assert detail_full["detail_level"] == "full"
        assert "export class AuthService" in detail_full["code"]
        assert "this.token = token;" in detail_full["code"]

    def test_extract_symbol_source_detail_syntax_error_fallback(self, tmp_path):
        from kortext.symbols.seek import extract_symbol_source_detail

        # Python file containing invalid syntax (e.g. malformed or partial code)
        bad_file = tmp_path / "broken.py"
        bad_file.write_text("def broken_func(:\n    ???\n")

        detail = extract_symbol_source_detail(
            file_path=str(bad_file),
            line=1,
            end_line=2,
            kind="function",
            signature="def broken_func()",
            docstring="A broken function with invalid syntax.",
            callers=[],
            callees=[],
            detail_level="skeleton",
        )
        # Should gracefully fall back to signature + docstring without crashing
        assert detail["detail_level"] == "skeleton"
        assert "def broken_func" in detail["code"]
        assert "A broken function with invalid syntax." in detail["code"]


class TestDeleteFileAst:
    """Tests for cascading FalkorDB AST deletion and ghost call purging."""

    def test_delete_file_ast_cascades_and_purges_orphans(self):
        from kortext.symbols.graph import SymbolGraphManager
        import uuid

        gname = f"test_graph_{uuid.uuid4().hex[:8]}"
        mgr = SymbolGraphManager(graph_name=gname)
        try:
            # 1. Set up two files with shared and isolated symbols, sections, calls
            file_a = "/workspace/src/module_a.py"
            file_b = "/workspace/src/module_b.py"

            mgr.save_file_ast(
                file_path=file_a,
                declarations=[
                    {"name": "unique_func_a", "kind": "function", "line": 10},
                    {"name": "shared_func", "kind": "function", "line": 20},
                ],
                imports=[],
                references=[
                    {"symbol": "target_func", "line": 15, "caller": "unique_func_a"},
                ],
            )

            mgr.save_file_ast(
                file_path=file_b,
                declarations=[
                    {"name": "unique_func_b", "kind": "function", "line": 30},
                    {"name": "shared_func", "kind": "function", "line": 40},
                ],
                imports=[],
                references=[],
            )

            # Add a section to file_a
            mgr._query(
                "MATCH (f:File {path: $path}) "
                "CREATE (sec:Section {id: 'sec_1', name: 'Header', path: $path}) "
                "CREATE (f)-[:CONTAINS_SECTION]->(sec)",
                {"path": file_a},
            )

            # Verify initial state
            defs_a = mgr.find_definition("unique_func_a")
            assert len(defs_a) == 1
            defs_shared = mgr.find_definition("shared_func")
            assert len(defs_shared) == 2

            calls_res = mgr._query(
                "MATCH ()-[r:CALLS {file_path: $path}]->() RETURN count(r)",
                {"path": file_a},
            )
            assert calls_res[1][0][0] >= 1

            # Act: Delete file_a AST
            mgr.delete_file_ast(file_a)

            # Assert:
            # 1. file_a File node is removed
            f_res = mgr._query("MATCH (f:File {path: $path}) RETURN count(f)", {"path": file_a})
            assert f_res[1][0][0] == 0

            # 2. Section node is removed
            sec_res = mgr._query("MATCH (sec:Section {id: 'sec_1'}) RETURN count(sec)")
            assert sec_res[1][0][0] == 0

            # 3. CALLS edges originating from file_a are purged
            calls_after = mgr._query(
                "MATCH ()-[r:CALLS {file_path: $path}]->() RETURN count(r)",
                {"path": file_a},
            )
            assert calls_after[1][0][0] == 0

            # 4. unique_func_a is purged from Symbol nodes
            sym_a = mgr._query("MATCH (s:Symbol {name: 'unique_func_a'}) RETURN count(s)")
            assert sym_a[1][0][0] == 0

            # 5. shared_func is preserved because it is still defined in file_b
            sym_shared = mgr._query("MATCH (s:Symbol {name: 'shared_func'}) RETURN count(s)")
            assert sym_shared[1][0][0] == 1
            defs_shared_after = mgr.find_definition("shared_func")
            assert len(defs_shared_after) == 1
            assert defs_shared_after[0]["file_path"] == file_b

            # 6. file_b is untouched
            f_b_res = mgr._query("MATCH (f:File {path: $path}) RETURN count(f)", {"path": file_b})
            assert f_b_res[1][0][0] == 1
        finally:
            mgr._query("MATCH (n) DETACH DELETE n")

    def test_save_file_ast_purges_stale_calls(self):
        from kortext.symbols.graph import SymbolGraphManager
        import uuid

        gname = f"test_graph_{uuid.uuid4().hex[:8]}"
        mgr = SymbolGraphManager(graph_name=gname)
        try:
            file_a = "/workspace/src/runner.py"

            # First save with a call to old_target
            mgr.save_file_ast(
                file_path=file_a,
                declarations=[{"name": "worker", "kind": "function", "line": 1}],
                imports=[],
                references=[{"symbol": "old_target", "line": 2, "caller": "worker"}],
            )

            calls_1 = mgr._query(
                "MATCH (c:Symbol {name: 'worker'})-[r:CALLS {file_path: $path}]->(s:Symbol {name: 'old_target'}) RETURN count(r)",
                {"path": file_a},
            )
            assert calls_1[1][0][0] == 1

            # Second save without the call (refactored)
            mgr.save_file_ast(
                file_path=file_a,
                declarations=[{"name": "worker", "kind": "function", "line": 1}],
                imports=[],
                references=[{"symbol": "new_target", "line": 3, "caller": "worker"}],
            )

            # old_target call should be purged
            calls_old = mgr._query(
                "MATCH (c:Symbol {name: 'worker'})-[r:CALLS {file_path: $path}]->(s:Symbol {name: 'old_target'}) RETURN count(r)",
                {"path": file_a},
            )
            assert calls_old[1][0][0] == 0

            # new_target call should exist
            calls_new = mgr._query(
                "MATCH (c:Symbol {name: 'worker'})-[r:CALLS {file_path: $path}]->(s:Symbol {name: 'new_target'}) RETURN count(r)",
                {"path": file_a},
            )
            assert calls_new[1][0][0] == 1
        finally:
            mgr._query("MATCH (n) DETACH DELETE n")
