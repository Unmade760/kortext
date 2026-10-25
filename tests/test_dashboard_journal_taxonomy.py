"""
Unit tests for Journal Category Extraction and Taxonomy Classification.
Validates that journal tags, titles, folders, and metadata map accurately
to the 8 canonical categories without defaulting everything to implementation.
"""

from pathlib import Path
import pytest

from kortext.dashboard.routes.journal import (
    _extract_category,
    VALID_CATEGORIES,
    CATEGORY_FOLDER_MAP,
)


class TestJournalCategoryExtraction:
    def test_explicit_category_metadata_takes_highest_precedence(self):
        body = "**Category:** decision\n\nSome implementation work."
        assert _extract_category(body) == "decision"

        body_bracket = "[Category: roadmap]\n\nSome plan."
        assert _extract_category(body_bracket) == "roadmap"

    def test_folder_hint_determines_category_when_no_explicit_metadata(self):
        body = "Completed various tasks today."
        assert _extract_category(body, folder_hint="decisions") == "decision"
        assert _extract_category(body, folder_hint="roadmaps") == "roadmap"
        assert _extract_category(body, folder_hint="investigations") == "investigation"
        assert _extract_category(body, folder_hint="benchmarks") == "benchmark"
        assert _extract_category(body, folder_hint="research") == "research"
        assert _extract_category(body, folder_hint="reports") == "report"
        assert _extract_category(body, folder_hint="dreams") == "report"
        assert _extract_category(body, folder_hint="handoffs") == "report"

    def test_tags_determine_category_accurately(self):
        # Tags line with roadmap should be roadmap, not implementation
        body = "Completed assessment.\n\n**Tags:** audit, architecture, roadmap, onboarding"
        assert _extract_category(body) == "roadmap"

        # Tags line with decision / adr
        body = "Evaluated vector stores.\n\n**Tags:** decision, adr, qdrant"
        assert _extract_category(body) == "decision"

        # Tags line with investigation / debugging
        body = "Diagnosed socket collision.\n\n**Tags:** investigation, debugging, sockets"
        assert _extract_category(body) == "investigation"

        # Tags line with benchmark / latency
        body = "Measured 5-signal retrieval.\n\n**Tags:** benchmark, latency, rrf"
        assert _extract_category(body) == "benchmark"

        # Tags line with research / survey
        body = "Explored HippoRAG algorithms.\n\n**Tags:** research, hipporag, ppr"
        assert _extract_category(body) == "research"

    def test_title_semantics_guide_category_classification(self):
        title = "06:30 - Completed Kortext Architectural Assessment and 6-Bucket Roadmap"
        body = "Conducted comprehensive codebase onboarding and established roadmap."
        assert _extract_category(body, title_hint=title) == "roadmap"

        title_adr = "ADR 004: Standardize on Unix Domain Sockets for FalkorDB"
        body = "Evaluated IPC transport trade-offs."
        assert _extract_category(body, title_hint=title_adr) == "decision"

        title_debug = "Investigated and Fixed Socket Collision in Watcher"
        body = "Resolved socket timeout bug."
        assert _extract_category(body, title_hint=title_debug) == "investigation"

    def test_fallback_to_implementation_when_no_specialized_category(self):
        body = "Implemented new feature and refactored helper functions.\n\n**Tags:** feature, code"
        assert _extract_category(body) == "implementation"

    def test_all_categories_in_valid_set(self):
        for cat in ["decision", "roadmap", "implementation", "experiment", "benchmark", "investigation", "research", "report"]:
            assert cat in VALID_CATEGORIES
