"""
Empirical benchmark comparing realistic ripgrep search token consumption against deterministic AST seek.
Populates session benchmark_store with real measured metrics rather than synthetic constants.
"""

import re
import shutil
import subprocess
from pathlib import Path
import pytest

from kortext.chunking.token_utils import count_tokens
from kortext.retrieval.engine import (
    K_RRF,
    W_AST,
    W_BM25,
    W_DENSE,
    W_HIPPO,
    W_TEMPORAL,
    apply_taak_trimming,
)
from kortext.symbols.seek import SymbolSeekEngine


def _simulate_rg_with_context(project_root: Path, target_dir_rel: str, pattern: str, context_lines: int = 3) -> str:
    """Realistic text search simulating `rg --no-heading -n -C <context_lines> <pattern> <target_dir_rel>`."""
    output_lines = []
    target_dir = project_root / target_dir_rel
    try:
        regex = re.compile(pattern)
    except re.error:
        regex = None

    for p in sorted(target_dir.rglob("*.py")):
        if not p.is_file() or "__pycache__" in p.parts:
            continue
        try:
            rel_str = str(p.relative_to(project_root))
            file_lines = p.read_text(encoding="utf-8", errors="ignore").splitlines()
            for idx, line in enumerate(file_lines):
                matched = regex.search(line) if regex is not None else (pattern in line)
                if matched:
                    start_i = max(0, idx - context_lines)
                    end_i = min(len(file_lines), idx + context_lines + 1)
                    for c_i in range(start_i, end_i):
                        output_lines.append(f"{rel_str}:{c_i + 1}:{file_lines[c_i]}")
        except Exception:
            continue
    return "\n".join(output_lines)


def _run_rg_or_fallback(project_root: Path, pkg_dir: str, symbol: str, context_lines: int = 3) -> str:
    if shutil.which("rg"):
        res = subprocess.run(
            ["rg", "--no-heading", "-n", "-C", str(context_lines), symbol, pkg_dir],
            cwd=project_root,
            capture_output=True,
            text=True,
        )
        if res.returncode == 0 and res.stdout.strip():
            return res.stdout
    return _simulate_rg_with_context(project_root, pkg_dir, symbol, context_lines=context_lines)


class TestTokenReductionBenchmark:
    def test_anti_ripgrep_token_reduction_ratio(self, benchmark_store):
        """TR-1: Multi-symbol live ripgrep (-C 3) vs deterministic AST seek_symbol skeleton token ratio."""
        project_root = Path(__file__).resolve().parent.parent
        engine = SymbolSeekEngine()
        symbols = ["RetrievalEngine", "TaskDAGTracker", "SymbolSeekEngine", "CausalSanitizer", "DreamEngine"]

        rg_counts = []
        seek_counts = []
        for sym in symbols:
            rg_out = _run_rg_or_fallback(project_root, "kortext", sym, context_lines=3)
            seek_out = engine.seek_symbol(sym, detail_level="skeleton")
            rg_counts.append(max(1, count_tokens(rg_out)))
            seek_counts.append(max(1, count_tokens(seek_out)))

        total_ripgrep_tokens = sum(rg_counts)
        total_kortext_tokens = sum(seek_counts)
        savings_ratio = (total_ripgrep_tokens - total_kortext_tokens) / total_ripgrep_tokens

        benchmark_store["token_reduction"]["TR-1_multi_symbol_rg_vs_seek_savings_pct"] = round(savings_ratio * 100.0, 2)
        assert savings_ratio >= 0.70, f"Expected >=70% token reduction across real symbols, got {savings_ratio * 100:.1f}%"

    def test_live_ripgrep_vs_seek_symbol_token_ratio(self, benchmark_store):
        """TR-2: Live ripgrep (-C 3) vs deterministic AST seek_symbol token ratio without full-file inflation."""
        project_root = Path(__file__).resolve().parent.parent
        rg_stdout = _run_rg_or_fallback(project_root, "kortext", "RetrievalEngine", context_lines=3)
        rg_tokens = max(1, count_tokens(rg_stdout))

        engine = SymbolSeekEngine()
        seek_output = engine.seek_symbol("RetrievalEngine", detail_level="skeleton")
        seek_tokens = max(1, count_tokens(seek_output))

        savings_ratio = (rg_tokens - seek_tokens) / rg_tokens
        benchmark_store["token_reduction"]["TR-2_live_rg_vs_seek_savings_pct"] = f"{savings_ratio * 100:.1f}% ({rg_tokens} -> {seek_tokens} tokens)"
        assert savings_ratio >= 0.75, f"Savings ratio {savings_ratio:.4f} is below 0.75 threshold"

    def test_taak_trimming_token_reduction(self, benchmark_store):
        """TR-3: Truncation-Aware Adaptive Knee (TAA-k) token reduction."""
        high_candidates = [(f"High scoring candidate {i}: " + "X" * 175, 0.046 - 0.001 * i) for i in range(3)]
        low_candidates = [(f"Low scoring candidate {j}: " + "Y" * 275, 0.0035 - 0.0001 * j) for j in range(12)]
        candidates = high_candidates + low_candidates

        before_text = "\n".join(c[0] for c in candidates)
        before_tokens = count_tokens(before_text)

        trimmed_texts = apply_taak_trimming(candidates, k_min=3, k_max=15)
        assert len(trimmed_texts) == 3, f"Expected 3 candidates after knee trimming, got {len(trimmed_texts)}"

        after_text = "\n".join(trimmed_texts)
        after_tokens = count_tokens(after_text)

        reduction_ratio = (before_tokens - after_tokens) / before_tokens
        benchmark_store["token_reduction"]["TR-3_taak_trimming_reduction_pct"] = f"{reduction_ratio * 100:.1f}%"
        assert reduction_ratio >= 0.50, f"Token reduction ratio {reduction_ratio:.4f} is below 0.50 threshold"

    def test_rrf_fusion_deduplication_ratio(self, benchmark_store):
        """TR-4: 5-Signal Reciprocal Rank Fusion deduplication ratio using production rank_candidates_rrf."""
        from kortext.retrieval.fusion import rank_candidates_rrf

        engine = SymbolSeekEngine()
        real_syms = ["RetrievalEngine", "SymbolSeekEngine", "TaskDAGTracker", "CausalSanitizer", "HippoRAGPPR", "FalkorDBClient"]
        base_passages = [engine.seek_symbol(s, detail_level="skeleton") for s in real_syms]
        extra_passages = [f"# File: kortext/module_{i}.py\ndef helper_{i}(): pass" for i in range(1, 10)]
        pool = base_passages + extra_passages  # 15 unique real/code passages

        ast_passages = pool[0:6]
        bm25_passages = pool[3:9]
        dense_passages = pool[6:12]
        hippo_passages = pool[9:15]
        temporal_passages = [pool[i] for i in (0, 2, 4, 7, 10, 13)]

        all_signals = [
            (ast_passages, W_AST),
            (bm25_passages, W_BM25),
            (dense_passages, W_DENSE),
            (hippo_passages, W_HIPPO),
            (temporal_passages, W_TEMPORAL),
        ]

        total_raw = sum(len(passages) for passages, _ in all_signals)
        assert total_raw == 30

        ranked = rank_candidates_rrf(all_signals)

        unique_count = len(ranked)
        assert unique_count == 15
        deduplication_reduction_ratio = (total_raw - unique_count) / total_raw
        benchmark_store["token_reduction"]["TR-4_rrf_deduplication_ratio"] = f"{deduplication_reduction_ratio * 100:.1f}%"
        assert deduplication_reduction_ratio >= 0.20
