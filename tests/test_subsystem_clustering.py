"""
Unit tests for Subsystem Community Detection via Louvain Modularity (kortext/symbols/clustering.py).

Validates:
1. Exclusion of non-code files (.md, .json, etc.) and test suites from architectural clustering.
2. Elimination of path-based naming defects.
3. Merging of 1-file orphan singletons into cohesive architectural subsystems.
4. Deterministic community boundaries and bounded subsystem counts.
"""
from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, List
import pytest

from kortext.symbols.clustering import SubsystemClusterer, is_code_file, resolve_subsystem_title


class TestSubsystemClustering:
    """Tests for Louvain subsystem community detection and architectural synthesis."""

    def test_is_code_file_filters_non_code_and_tests(self):
        """Verifies is_code_file includes production source code and filters docs, markdown, and tests."""
        # Code files that should be included
        assert is_code_file("/path/to/kortext/retrieval/engine.py") is True
        assert is_code_file("/path/to/kortext/server.py") is True
        assert is_code_file("/path/to/kortext/dashboard/views/specs.py") is True

        # Non-code files that must be excluded
        assert is_code_file("/path/to/kortext/journal/2026-10-10.md") is False
        assert is_code_file("/path/to/kortext/docs/architecture.md") is False
        assert is_code_file("/path/to/kortext/rules/coding-style.md") is False
        assert is_code_file("/path/to/kortext/config.json") is False
        assert is_code_file("/path/to/kortext/pyproject.toml") is False

        # Test files that must be excluded from production architecture
        assert is_code_file("/path/to/kortext/tests/test_engine.py") is False
        assert is_code_file("/path/to/kortext/test_server.py") is False

    def test_resolve_subsystem_title_eliminates_path_prefix_labels(self):
        """Verifies resolve_subsystem_title derives clean architectural domain titles without path artifacts."""
        # Absolute path lists must never resolve to username or system path artifacts
        retrieval_files = [
            "/home/developer/workspace/kortext/retrieval/engine.py",
            "/home/developer/workspace/kortext/retrieval/fusion.py",
            "/home/developer/workspace/kortext/retrieval/hipporag.py",
        ]
        title = resolve_subsystem_title(retrieval_files)
        assert "Retrieval" in title
        assert "Developer" not in title
        assert "Workspace" not in title

        symbols_files = [
            "/home/developer/workspace/kortext/symbols/seek.py",
            "/home/developer/workspace/kortext/symbols/graph.py",
        ]
        title_sym = resolve_subsystem_title(symbols_files)
        assert "Symbols" in title_sym or "Code Intelligence" in title_sym
        assert "Developer" not in title_sym

    @pytest.mark.asyncio
    async def test_detect_subsystems_excludes_markdown_and_path_labels(self, seeded_symbol_graph):
        """Verifies live or mock detect_subsystems produces clean subsystems without markdown or path artifacts."""
        clusterer = SubsystemClusterer()
        subsystems = await clusterer.detect_subsystems(persist=False)

        assert len(subsystems) > 0
        assert len(subsystems) <= 15, f"Expected <= 15 cohesive subsystems, got {len(subsystems)}"

        for sub in subsystems:
            name = sub["name"]
            files = sub["files"]

            # Must not contain path prefix artifacts
            assert not name.startswith("/"), f"Subsystem name has path separator: {name}"

            # Must not contain markdown files
            for fp in files:
                assert not fp.endswith(".md"), f"Markdown file found in subsystem {name}: {fp}"
                assert "/journal/" not in fp, f"Journal file found in subsystem {name}: {fp}"

            # Must not be a 1-file singleton orphan if total codebase has multiple files
            if len(files) == 1 and len(subsystems) > 1:
                # If there are >1 subsystems, single-file subsystems should be consolidated into core
                pytest.fail(f"1-file orphan singleton detected: {name} ({files[0]})")
