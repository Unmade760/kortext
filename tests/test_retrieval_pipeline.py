"""
Unit tests for 5-Signal Hybrid RRF Retrieval Pipeline and TAA-k Trimming.
"""

import pytest
from cerebrum.retrieval.engine import (
    apply_taak_trimming,
    RetrievalEngine,
    extract_passage_text,
    K_RRF,
    W_AST,
    W_DENSE,
)


class TestRetrievalPipeline:
    def test_taak_trimming_cliff_detection(self):
        """Verifies TAA-k correctly detects score drop and drops distractor passages."""
        # 3 high relevance docs, followed by sudden cliff, then low score distractors
        scored = [
            ("doc1", 0.045),
            ("doc2", 0.042),
            ("doc3", 0.040),
            ("distractor1", 0.005),
            ("distractor2", 0.004),
            ("distractor3", 0.003),
        ]
        trimmed = apply_taak_trimming(scored, k_min=3, k_max=15)
        # Should cut off at 3 docs
        assert trimmed == ["doc1", "doc2", "doc3"]

    def test_taak_trimming_minimum_floor(self):
        """Verifies that k_min is respected even if cliff is earlier."""
        scored = [
            ("doc1", 0.9),
            ("doc2", 0.1),
            ("doc3", 0.09),
            ("doc4", 0.08),
        ]
        trimmed = apply_taak_trimming(scored, k_min=3, k_max=10)
        assert len(trimmed) >= 3

    def test_extract_passage_text(self):
        assert extract_passage_text({"text": "hello world"}) == "hello world"
        assert extract_passage_text({"document": "doc body"}) == "doc body"
        assert extract_passage_text({"_node_content": '{"text": "node content"}'}) == "node content"

    def test_symbol_candidate_extraction(self):
        engine = RetrievalEngine()
        query = "Where is the definition of `RetrievalEngine` and what calls SymbolSeekEngine?"
        candidates = engine._extract_symbol_candidates(query)
        assert "RetrievalEngine" in candidates
        assert "SymbolSeekEngine" in candidates
