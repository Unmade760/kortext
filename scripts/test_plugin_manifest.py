#!/usr/bin/env python3
"""
Test Suite for Kortext Antigravity Plugin Manifests & Schemas.
"""
import json
import re
from pathlib import Path

KORTEXT_ROOT = Path(__file__).resolve().parent.parent
PLUGIN_DIR = KORTEXT_ROOT / "integrations" / "antigravity"

def test_plugin_json():
    p = PLUGIN_DIR / "plugin.json"
    assert p.is_file(), "plugin.json must exist"
    data = json.loads(p.read_text())
    assert data.get("name") in ("kortext", "cerebrum"), f"Plugin name must be kortext or cerebrum, got {data.get('name')}"
    assert re.match(r"^[a-zA-Z0-9-_]+$", data["name"]), "Plugin name must match regex"
    assert "description" in data, "Plugin description required"
    assert "mcpServers" not in data, "mcpServers must NOT be declared in plugin.json (use mcp_config.json per Antigravity spec)"
    allowed_keys = {"$schema", "name", "description"}
    extra_keys = set(data.keys()) - allowed_keys
    assert not extra_keys, f"plugin.json contains unexpected keys: {extra_keys}"
    print("✅ plugin.json schema valid.")

def test_mcp_config():
    assert not (PLUGIN_DIR / "mcp_config.json").exists(), "Plugin mcp_config.json should not exist to avoid plugin namespace duplication"
    host_mcp = Path.home() / ".gemini" / "config" / "mcp_config.json"
    if host_mcp.exists():
        data = json.loads(host_mcp.read_text())
        assert "mcpServers" in data, "mcpServers must be defined in mcp_config.json"
        assert isinstance(data["mcpServers"], dict), "mcpServers must be a dictionary"
        assert "kortext" in data["mcpServers"], "kortext must be configured in mcpServers"
        assert "cerebrum_kortext" not in data["mcpServers"], "cerebrum_kortext must not be in mcpServers"
        assert "kortext_kortext" not in data["mcpServers"], "kortext_kortext must not be in mcpServers"
    print("✅ Single canonical kortext MCP server verified in host mcp_config.json.")

def test_hooks_json():
    p = PLUGIN_DIR / "hooks.json"
    assert p.is_file(), "hooks.json must exist"
    data = json.loads(p.read_text())
    expected_hooks = [
        "ambient-grounding",
        "safety-gate",
        "cache-invalidation",
        "dag-stop-guard"
    ]
    for h in expected_hooks:
        assert f"kortext-{h}" in data or f"cerebrum-{h}" in data, f"Hook {h} must be configured"
    print("✅ hooks.json definitions valid.")

def test_subagent_yaml():
    agents_dir = PLUGIN_DIR / "agents"
    canonical_files = {
        "kortext-architect.md",
        "kortext-code-reviewer.md",
        "kortext-researcher.md",
        "kortext-task-runner.md",
        "kortext-security-auditor.md",
    }
    found_files = {p.name for p in agents_dir.glob("*.md")}
    assert found_files == canonical_files, f"Expected exactly {canonical_files}, got {found_files}"

    cerebrum_files = list(agents_dir.glob("cerebrum-*.md"))
    assert not cerebrum_files, f"Deprecated cerebrum agent files found: {cerebrum_files}"

    for filename in sorted(canonical_files):
        p = agents_dir / filename
        assert p.is_file(), f"{filename} must exist"
        text = p.read_text()
        assert text.startswith("---"), f"{p.name} must start with YAML frontmatter"
        assert "name:" in text, f"{p.name} missing 'name:'"
        assert "description:" in text, f"{p.name} missing 'description:'"
        assert "model:" in text, f"{p.name} missing 'model:'"
        assert "subagent: true" in text, f"{p.name} missing 'subagent: true'"
        assert "mainAgent: false" in text, f"{p.name} missing 'mainAgent: false'"
    print("✅ agents/*.md YAML frontmatters valid.")

def test_skills_yaml():
    for name in ["anti-ripgrep-seek", "task-orchestrator"]:
        p = PLUGIN_DIR / "skills" / name / "SKILL.md"
        assert p.is_file(), f"{name}/SKILL.md must exist"
    assert (PLUGIN_DIR / "skills" / "kortext-rag" / "SKILL.md").is_file(), "kortext-rag/SKILL.md must exist"
    assert (PLUGIN_DIR / "skills" / "kortext-architect" / "SKILL.md").is_file(), "kortext-architect/SKILL.md must exist"
    assert not (PLUGIN_DIR / "skills" / "cerebrum-rag").exists(), "cerebrum-rag directory must not exist"
    assert not (PLUGIN_DIR / "skills" / "cerebrum-architect").exists(), "cerebrum-architect directory must not exist"
    for skill_file in (PLUGIN_DIR / "skills").glob("*/SKILL.md"):
        text = skill_file.read_text()
        assert text.startswith("---"), f"{skill_file} must start with YAML frontmatter"
        assert "name: " in text
        assert "description:" in text
    print("✅ skills/*/SKILL.md YAML frontmatters valid.")

def test_sidecars_json():
    sidecars_dir = PLUGIN_DIR / "sidecars"
    assert sidecars_dir.is_dir(), "sidecars directory must exist"
    
    expected_sidecars = ["kortext-watcher", "kortext-dream"]
    for sidecar_name in expected_sidecars:
        sc_dir = sidecars_dir / sidecar_name
        assert sc_dir.is_dir(), f"Sidecar directory {sidecar_name} must exist"
        
        manifest_path = sc_dir / "sidecar.json"
        assert manifest_path.is_file(), f"sidecar.json must exist for {sidecar_name}"
        
        try:
            data = json.loads(manifest_path.read_text())
        except json.JSONDecodeError as e:
            raise AssertionError(f"sidecar.json for {sidecar_name} is not valid JSON: {e}") from e
        
        assert "display_name" in data and isinstance(data["display_name"], str) and data["display_name"], (
            f"display_name must be a non-empty string in {sidecar_name}"
        )
        assert "description" in data and isinstance(data["description"], str) and data["description"], (
            f"description must be a non-empty string in {sidecar_name}"
        )
        assert "command" in data and isinstance(data["command"], str) and data["command"], (
            f"command must be specified as a non-empty string in {sidecar_name}"
        )
        assert "args" in data and isinstance(data["args"], list), (
            f"args must be a list in {sidecar_name}"
        )
        assert all(isinstance(a, str) for a in data["args"]), (
            f"all items in args must be strings in {sidecar_name}"
        )
        assert "restart_policy" in data and isinstance(data["restart_policy"], str), (
            f"restart_policy must be specified in {sidecar_name}"
        )
        assert data["restart_policy"] in ("always", "on-failure", "never", "unless-stopped"), (
            f"restart_policy '{data['restart_policy']}' is invalid in {sidecar_name}"
        )
        if "env" in data:
            assert isinstance(data["env"], dict), f"env must be a dict in {sidecar_name}"
            assert all(isinstance(k, str) and isinstance(v, str) for k, v in data["env"].items()), (
                f"env entries must be string key-value pairs in {sidecar_name}"
            )
            
    print("✅ sidecars/*/sidecar.json manifests valid.")

if __name__ == "__main__":
    print("=== Running Kortext Plugin Manifest Validation Suite ===")
    test_plugin_json()
    test_mcp_config()
    test_hooks_json()
    test_subagent_yaml()
    test_skills_yaml()
    test_sidecars_json()
    print("🎉 All Kortext manifest tests passed!")


