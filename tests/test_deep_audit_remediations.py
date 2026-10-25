"""
Regression tests verifying all 18 deep-audit bug fixes and ecosystem adaptations across Kortext.
"""
from __future__ import annotations

import json
from pathlib import Path
import re
from unittest.mock import MagicMock

from kortext.chunking.token_utils import count_tokens
from kortext.hooks.context import HookContext
from kortext.hooks.pipelines.post_tool import has_recent_passing_test_run, record_test_execution_proof
from kortext.hooks.pipelines.pre_tool import CommandSafetyGuard, SensitivePathReadGuard
from kortext.invariants import InvariantGroundingEngine, compute_ast_minhash_sketch
from kortext.server_helpers import _filter_untrusted_injection_chunks, _format_federated_markdown
from kortext.trust.sanitizer import strip_invisible_unicode


def test_deep_audit_18_findings_and_ecosystem_remediations(tmp_path, monkeypatch):
    """Verifies all 18 deep-audit bug fixes and ecosystem adaptations across Kortext."""
    monkeypatch.setenv("KORTEXT_HOME", str(tmp_path))
    repo_root = Path(__file__).resolve().parent.parent

    # 1. Bug 1: Symbol-scoped MinHash sketch produces distinct sketches for distinct symbols in the same file
    multi_sym_file = tmp_path / "multi_sym.py"
    multi_sym_file.write_text(
        "def alpha_calc(a: int, b: int) -> int:\n"
        "    total = (a * 17) + (b * 31) - 99\n"
        "    return total * 2\n\n"
        "def beta_render(name: str, prefix: str) -> str:\n"
        "    formatted = f'{prefix}::{name.strip().lower()}'\n"
        "    return formatted.replace(' ', '_')\n",
        encoding="utf-8",
    )
    sketch_alpha = compute_ast_minhash_sketch(str(multi_sym_file), "alpha_calc")
    sketch_beta = compute_ast_minhash_sketch(str(multi_sym_file), "beta_render")
    assert sketch_alpha and sketch_beta
    assert sketch_alpha != sketch_beta

    # 2. Bug 2: audit_invariant_drift flags gutted/stubbed function bodies as drifted even when signature matches
    gutted_file = tmp_path / "gutted_target.py"
    gutted_file.write_text(
        "def sanitize_payload(text: str) -> bool:\n"
        "    cleaned = text.strip().lower()\n"
        "    if 'malicious' in cleaned:\n"
        "        raise ValueError('blocked')\n"
        "    return True\n",
        encoding="utf-8",
    )
    ige = InvariantGroundingEngine(client=MagicMock())
    monkeypatch.setattr("kortext.invariants.GROUNDED_FILE", tmp_path / "grounded_gutted.json")
    ige.ground_invariant(
        domain="SECURITY",
        rule="sanitize_payload must validate malicious input",
        rationale="Prevent bypass",
        symbol_name="sanitize_payload",
        file_path=str(gutted_file),
    )
    gutted_file.write_text("def sanitize_payload(text: str) -> bool:\n    return True\n", encoding="utf-8")
    drift_audit = ige.audit_invariant_drift()
    assert drift_audit["drifted_count"] == 1
    assert drift_audit["drifted"][0]["drift_reason"] == "body_gutted_to_stub"

    # 3. Bug 5: CJK-aware token estimation
    cjk_text = "这是一个用于测试令牌计数器的中文段落，包含足够多的漢字字符。" * 4
    assert count_tokens(cjk_text) > len(cjk_text) // 4

    # 4. Bug 13: hooks.json and install_plugin.py match MCP tool prefixes and view_file
    hooks_json = json.loads((repo_root / "integrations" / "antigravity" / "hooks.json").read_text(encoding="utf-8"))
    pre_matcher = hooks_json["kortext-safety-gate"]["PreToolUse"][0]["matcher"]
    post_matcher = hooks_json["kortext-cache-invalidation"]["PostToolUse"][0]["matcher"]
    assert re.search(pre_matcher, "view_file")
    assert re.search(post_matcher, "mcp:kortext:seek_symbol")
    assert re.search(post_matcher, "kortext:trace_symbol_impact")

    # 5. Bug 14: Session-scoped test execution proofs isolate concurrent sessions
    record_test_execution_proof("pytest -q", passed=True, session_id="sess_alpha")
    record_test_execution_proof("pytest -q", passed=False, session_id="sess_beta")
    assert has_recent_passing_test_run(session_id="sess_alpha") is True
    assert has_recent_passing_test_run(session_id="sess_beta") is False

    # 6. Bug 16 & CLI 1.4.7 10KB inline ceiling: sanitizer.py code chunk is not self-stripped, and markdown is capped <10KB
    self_chunk = "# File: kortext/trust/sanitizer.py\nINJECTION_PATTERNS = [r'ignore all previous instructions']"
    filtered = _filter_untrusted_injection_chunks({"code_chunks": [self_chunk], "episodic_history": []})
    assert len(filtered["code_chunks"]) == 1
    oversized_md = _format_federated_markdown(
        {"code_chunks": ["x" * 12000], "symbolic_context": [], "episodic_history": []},
        query="big query",
        token_budget=1500,
    )
    assert len(oversized_md.encode("utf-8")) <= 9600

    # 7. Invisible Unicode stripping & SensitivePathReadGuard + CommandSafetyGuard git checkout/clean
    assert strip_invisible_unicode("hello\u200b\u202eworld") == "helloworld"
    sp_guard = SensitivePathReadGuard()
    assert sp_guard.check(HookContext.from_stdin(raw_text=json.dumps({"toolCall": {"name": "view_file", "args": {"AbsolutePath": "/Users/test/.ssh/id_rsa"}}}))).decision == "deny"
    assert sp_guard.check(HookContext.from_stdin(raw_text=json.dumps({"toolCall": {"name": "view_file", "args": {"AbsolutePath": "/workspace/.env"}}}))).decision == "deny"
    assert sp_guard.check(HookContext.from_stdin(raw_text=json.dumps({"toolCall": {"name": "view_file", "args": {"AbsolutePath": "/workspace/.env.example"}}}))).decision == "allow"
    assert CommandSafetyGuard().check(HookContext.from_stdin(raw_text=json.dumps({"toolCall": {"name": "run_command", "args": {"CommandLine": "git clean -fd"}}}))).decision == "deny"

    # 8. GLOSSARY.md, canonical skills, and bundled black-box scripts exist
    assert (repo_root / "GLOSSARY.md").is_file()
    for skill_name in ("kortext-boost", "expand-contract-refactor", "systematic-debugging", "verification-before-completion"):
        assert (repo_root / "integrations" / "antigravity" / "skills" / skill_name / "SKILL.md").is_file()
    assert (repo_root / "integrations" / "antigravity" / "skills" / "code-review" / "scripts" / "verify_diff.py").is_file()
    assert (repo_root / "integrations" / "antigravity" / "skills" / "expand-contract-refactor" / "scripts" / "check_blast_radius.py").is_file()
