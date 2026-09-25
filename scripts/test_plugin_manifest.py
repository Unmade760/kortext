#!/usr/bin/env python3
"""
Test Suite for Cerebrum Antigravity Plugin Manifests & Schemas.
"""
import json
import re
from pathlib import Path

PLUGIN_DIR = Path(__file__).resolve().parent.parent / "integrations" / "antigravity"

def test_plugin_json():
    p = PLUGIN_DIR / "plugin.json"
    assert p.is_file(), "plugin.json must exist"
    data = json.loads(p.read_text())
    assert data.get("name") == "cerebrum", "Plugin name must be cerebrum"
    assert re.match(r"^[a-zA-Z0-9-_]+$", data["name"]), "Plugin name must match regex"
    assert "description" in data, "Plugin description required"
    print("✅ plugin.json schema valid.")

def test_hooks_json():
    p = PLUGIN_DIR / "hooks.json"
    assert p.is_file(), "hooks.json must exist"
    data = json.loads(p.read_text())
    expected_hooks = [
        "cerebrum-ambient-grounding",
        "cerebrum-safety-gate",
        "cerebrum-cache-invalidation",
        "cerebrum-dag-stop-guard"
    ]
    for h in expected_hooks:
        assert h in data, f"Hook {h} must be configured"
    print("✅ hooks.json definitions valid.")

def test_subagent_yaml():
    for name in ["cerebrum-researcher.md", "cerebrum-architect.md", "cerebrum-code-reviewer.md", "cerebrum-task-runner.md"]:
        p = PLUGIN_DIR / "agents" / name
        assert p.is_file(), f"{name} must exist"
        text = p.read_text()
        assert text.startswith("---"), f"{name} must start with YAML frontmatter"
        assert "name:" in text
        assert "description:" in text
        assert "model:" in text
    print("✅ agents/*.md YAML frontmatters valid.")

def test_skills_yaml():
    for name in ["cerebrum-rag", "cerebrum-architect", "anti-ripgrep-seek", "task-orchestrator"]:
        p = PLUGIN_DIR / "skills" / name / "SKILL.md"
        assert p.is_file(), f"{name}/SKILL.md must exist"
        text = p.read_text()
        assert text.startswith("---"), f"{name} must start with YAML frontmatter"
        assert f"name: {name}" in text
        assert "description:" in text
    print("✅ skills/*/SKILL.md YAML frontmatters valid.")

if __name__ == "__main__":
    print("=== Running Cerebrum Plugin Manifest Validation Suite ===")
    test_plugin_json()
    test_hooks_json()
    test_subagent_yaml()
    test_skills_yaml()
    print("🎉 All Cerebrum manifest tests passed!")
