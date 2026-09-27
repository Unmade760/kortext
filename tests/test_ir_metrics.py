"""
Unit tests for cerebrum.benchmarks.ir_metrics.

Verifies Information Retrieval & QA evaluation metrics:
- recall_at_k
- precision_at_k
- mean_reciprocal_rank
- ndcg_at_k
- exact_match
- token_f1
"""

from __future__ import annotations

import math
import pytest

from cerebrum.benchmarks.ir_metrics import (
    exact_match,
    mean_reciprocal_rank,
    ndcg_at_k,
    precision_at_k,
    recall_at_k,
    token_f1,
)


class TestRecallAtK:
    """Tests for recall_at_k."""

    def test_perfect_score(self):
        retrieved = ["doc1", "doc2", "doc3"]
        gold = ["doc1", "doc2"]
        assert recall_at_k(retrieved, gold, k=2) == 1.0
        assert recall_at_k(retrieved, gold, k=3) == 1.0

    def test_empty_inputs(self):
        assert recall_at_k([], ["doc1"], k=5) == 0.0
        assert recall_at_k(["doc1"], [], k=5) == 0.0
        assert recall_at_k([], [], k=5) == 0.0

    def test_disjoint(self):
        retrieved = ["doc1", "doc2"]
        gold = ["doc3", "doc4"]
        assert recall_at_k(retrieved, gold, k=2) == 0.0

    def test_partial(self):
        retrieved = ["doc1", "doc2", "doc3"]
        gold = ["doc1", "doc4"]
        # 1 out of 2 gold retrieved in top 2
        assert recall_at_k(retrieved, gold, k=2) == 0.5
        # 1 out of 2 gold retrieved in top 3
        assert recall_at_k(retrieved, gold, k=3) == 0.5

        # 2 out of 3 gold retrieved
        retrieved_long = ["doc1", "doc2", "docX", "doc3"]
        gold_three = ["doc1", "doc2", "doc3"]
        assert recall_at_k(retrieved_long, gold_three, k=2) == pytest.approx(2 / 3)

    def test_k_bounds(self):
        retrieved = ["doc1", "doc2"]
        gold = ["doc1", "doc2"]
        assert recall_at_k(retrieved, gold, k=0) == 0.0
        assert recall_at_k(retrieved, gold, k=-1) == 0.0
        # k larger than retrieved list length
        assert recall_at_k(retrieved, gold, k=10) == 1.0
        # k cut off before some relevant items
        assert recall_at_k(retrieved, gold, k=1) == 0.5

    def test_duplicates_handling(self):
        # Duplicates in retrieved should not artificially inflate recall
        retrieved = ["doc1", "doc1", "doc2"]
        gold = ["doc1", "doc2"]
        assert recall_at_k(retrieved, gold, k=2) == 0.5
        assert recall_at_k(retrieved, gold, k=3) == 1.0

        # Duplicates in gold
        retrieved_clean = ["doc1"]
        gold_dup = ["doc1", "doc1"]
        assert recall_at_k(retrieved_clean, gold_dup, k=1) == 1.0


class TestPrecisionAtK:
    """Tests for precision_at_k."""

    def test_perfect_score(self):
        retrieved = ["doc1", "doc2", "doc3"]
        gold = ["doc1", "doc2", "doc3"]
        assert precision_at_k(retrieved, gold, k=3) == 1.0
        assert precision_at_k(retrieved, gold, k=2) == 1.0

    def test_empty_inputs(self):
        assert precision_at_k([], ["doc1"], k=5) == 0.0
        assert precision_at_k(["doc1"], [], k=5) == 0.0
        assert precision_at_k([], [], k=5) == 0.0

    def test_disjoint(self):
        retrieved = ["doc1", "doc2"]
        gold = ["doc3", "doc4"]
        assert precision_at_k(retrieved, gold, k=2) == 0.0

    def test_partial(self):
        retrieved = ["doc1", "doc2", "doc3", "doc4"]
        gold = ["doc1", "doc3"]
        # In top 2: doc1 is relevant, doc2 is not -> 1/2 = 0.5
        assert precision_at_k(retrieved, gold, k=2) == 0.5
        # In top 4: doc1, doc3 are relevant -> 2/4 = 0.5
        assert precision_at_k(retrieved, gold, k=4) == 0.5
        # In top 3: doc1, doc3 are relevant -> 2/3 ≈ 0.6667
        assert precision_at_k(retrieved, gold, k=3) == pytest.approx(2 / 3)

    def test_k_bounds(self):
        retrieved = ["doc1", "doc2"]
        gold = ["doc1", "doc2"]
        assert precision_at_k(retrieved, gold, k=0) == 0.0
        assert precision_at_k(retrieved, gold, k=-5) == 0.0
        # If k exceeds retrieved length, precision denominator is k
        # retrieved has 2 relevant items, k=4 -> 2/4 = 0.5
        assert precision_at_k(retrieved, gold, k=4) == 0.5

    def test_duplicates_handling(self):
        # Duplicate doc in retrieved shouldn't count multiple times towards precision
        retrieved = ["doc1", "doc1", "doc2"]
        gold = ["doc1"]
        # In top 2: only 1 unique gold doc retrieved -> 1/2 = 0.5
        assert precision_at_k(retrieved, gold, k=2) == 0.5


class TestMeanReciprocalRank:
    """Tests for mean_reciprocal_rank."""

    def test_perfect_score(self):
        retrieved = ["doc1", "doc2", "doc3"]
        gold = ["doc1"]
        assert mean_reciprocal_rank(retrieved, gold) == 1.0

        # First doc in retrieved matches one of the gold items
        assert mean_reciprocal_rank(retrieved, ["doc3", "doc1"]) == 1.0

    def test_empty_inputs(self):
        assert mean_reciprocal_rank([], ["doc1"]) == 0.0
        assert mean_reciprocal_rank(["doc1"], []) == 0.0
        assert mean_reciprocal_rank([], []) == 0.0

    def test_disjoint(self):
        retrieved = ["doc1", "doc2"]
        gold = ["doc3", "doc4"]
        assert mean_reciprocal_rank(retrieved, gold) == 0.0

    def test_positions(self):
        # Rank 2
        assert mean_reciprocal_rank(["non1", "doc1"], ["doc1"]) == 0.5
        # Rank 3
        assert mean_reciprocal_rank(["non1", "non2", "doc1"], ["doc1"]) == pytest.approx(1 / 3)
        # Rank 4
        assert mean_reciprocal_rank(["non1", "non2", "non3", "doc1"], ["doc1"]) == 0.25
        # Multiple relevant: takes highest rank (earliest)
        assert mean_reciprocal_rank(["non1", "docA", "docB"], ["docB", "docA"]) == 0.5


class TestNdcgAtK:
    """Tests for ndcg_at_k."""

    def test_perfect_score(self):
        retrieved = ["doc1", "doc2", "doc3"]
        gold = ["doc1", "doc2"]
        # Top 2 results are the 2 relevant items
        assert ndcg_at_k(retrieved, gold, k=2) == 1.0
        assert ndcg_at_k(retrieved, gold, k=3) == 1.0
        assert ndcg_at_k(["doc1"], ["doc1"], k=1) == 1.0

    def test_empty_inputs(self):
        assert ndcg_at_k([], ["doc1"], k=5) == 0.0
        assert ndcg_at_k(["doc1"], [], k=5) == 0.0
        assert ndcg_at_k([], [], k=5) == 0.0

    def test_disjoint(self):
        retrieved = ["doc1", "doc2"]
        gold = ["doc3", "doc4"]
        assert ndcg_at_k(retrieved, gold, k=2) == 0.0

    def test_partial_and_ranking(self):
        # Relevant doc at rank 2 instead of rank 1
        retrieved = ["non1", "doc1"]
        gold = ["doc1"]
        # DCG@2 = 0 + 1 / log2(2 + 1) = 1 / log2(3)
        # IDCG@2 = 1 / log2(1 + 1) = 1 / 1 = 1.0
        expected = (1.0 / math.log2(3)) / 1.0
        assert ndcg_at_k(retrieved, gold, k=2) == pytest.approx(expected)

        # 2 gold docs, but retrieved only has 1 at rank 1
        retrieved_one = ["doc1", "non1"]
        gold_two = ["doc1", "doc2"]
        # DCG@2 = 1 / log2(2) = 1.0
        # IDCG@2 = 1 / log2(2) + 1 / log2(3)
        idcg = 1.0 / math.log2(2) + 1.0 / math.log2(3)
        expected_one = 1.0 / idcg
        assert ndcg_at_k(retrieved_one, gold_two, k=2) == pytest.approx(expected_one)

    def test_k_bounds(self):
        retrieved = ["doc1", "doc2"]
        gold = ["doc1"]
        assert ndcg_at_k(retrieved, gold, k=0) == 0.0
        assert ndcg_at_k(retrieved, gold, k=-2) == 0.0

        # Relevant doc at rank 2, but k=1 cutoff excludes it
        retrieved_lag = ["non1", "doc1"]
        assert ndcg_at_k(retrieved_lag, gold, k=1) == 0.0

        # k larger than retrieved length
        retrieved_short = ["doc1"]
        gold_multi = ["doc1", "doc2"]
        idcg_multi = 1.0 / math.log2(2) + 1.0 / math.log2(3)
        assert ndcg_at_k(retrieved_short, gold_multi, k=5) == pytest.approx(1.0 / idcg_multi)

    def test_duplicates_handling(self):
        # Duplicate doc in retrieved should not contribute multiple times to DCG
        retrieved = ["doc1", "doc1", "doc2"]
        gold = ["doc1"]
        # Only first doc1 counts at rank 1: DCG = 1.0, IDCG = 1.0
        assert ndcg_at_k(retrieved, gold, k=3) == 1.0


class TestExactMatch:
    """Tests for exact_match."""

    def test_perfect_score(self):
        assert exact_match("hello world", "hello world") == 1.0
        assert exact_match("Cerebrum System", "cerebrum system") == 1.0
        assert exact_match("Hello, World!", "hello world") == 1.0
        assert exact_match("  spaced   out   text\n", "spaced out text") == 1.0

    def test_empty_inputs(self):
        assert exact_match("", "") == 1.0
        assert exact_match("   ", "") == 1.0
        assert exact_match("!.,", "") == 1.0
        assert exact_match("hello", "") == 0.0
        assert exact_match("", "hello") == 0.0

    def test_disjoint(self):
        assert exact_match("apple", "orange") == 0.0

    def test_partial(self):
        assert exact_match("apple pie", "apple") == 0.0
        assert exact_match("the test", "test") == 0.0

    def test_punctuation_and_symbols(self):
        assert exact_match("U.S.A.", "usa") == 1.0
        assert exact_match("state-of-the-art", "stateoftheart") == 1.0
        assert exact_match("What... really?!", "what really") == 1.0


class TestTokenF1:
    """Tests for token_f1."""

    def test_perfect_score(self):
        assert token_f1("the quick brown fox", "The Quick Brown Fox") == 1.0
        assert token_f1("hello, world!", "hello world") == 1.0

    def test_empty_inputs(self):
        assert token_f1("", "") == 1.0
        assert token_f1("   ", "!!!") == 1.0
        assert token_f1("hello", "") == 0.0
        assert token_f1("", "world") == 0.0

    def test_disjoint(self):
        assert token_f1("apple banana", "cherry date") == 0.0

    def test_partial_overlap(self):
        # pred: ['the', 'brown', 'fox'] (len 3)
        # gold: ['the', 'quick', 'brown', 'fox'] (len 4)
        # overlap = 3
        # precision = 3/3 = 1.0, recall = 3/4 = 0.75
        # F1 = 2 * 1 * 0.75 / (1 + 0.75) = 1.5 / 1.75 = 6/7
        assert token_f1("the brown fox", "the quick brown fox") == pytest.approx(6 / 7)

        # pred: ['a', 'b'], gold: ['b', 'c']
        # overlap = 1, precision = 1/2, recall = 1/2 -> F1 = 0.5
        assert token_f1("a b", "b c") == pytest.approx(0.5)

    def test_duplicate_tokens(self):
        # pred has 2 'apple', gold has 1 'apple'
        # overlap = 1, precision = 1/2, recall = 1/1 -> F1 = 2*(0.5*1.0)/1.5 = 1/1.5 = 2/3
        assert token_f1("apple apple", "apple") == pytest.approx(2 / 3)

        # pred has 1 'apple', gold has 2 'apple'
        # overlap = 1, precision = 1/1 = 1.0, recall = 1/2 = 0.5 -> F1 = 2/3
        assert token_f1("apple", "apple apple") == pytest.approx(2 / 3)

    def test_punctuation_and_whitespace(self):
        assert token_f1("Hello, world! One, two.", "hello world one two") == 1.0
