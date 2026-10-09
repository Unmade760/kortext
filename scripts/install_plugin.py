#!/usr/bin/env python3
"""
Cerebrum Antigravity Plugin Dynamic Installer.
Generates machine-specific hooks.json and installs symlinks to Antigravity plugins.
"""
import json
import os
import shutil
import stat
from pathlib import Path

KORTEXT_ROOT = Path(__file__).resolve().parent.parent
CEREBRUM_ROOT = KORTEXT_ROOT
INTEGRATIONS_DIR = KORTEXT_ROOT / "integrations" / "antigravity"
SCRIPTS_DIR = KORTEXT_ROOT / "scripts" / "hooks"


def build_hooks_dict() -> dict:
    venv_py = KORTEXT_ROOT / ".venv" / "bin" / "python3"
    py_exec = str(venv_py) if venv_py.is_file() else "python3"
    return {
        "kortext-ambient-grounding": {
            "PreInvocation": [
                {
                    "type": "command",
                    "command": f"{py_exec} {SCRIPTS_DIR / 'hook_pre_invoke.py'}",
                    "timeout": 15,
                }
            ]
        },
        "kortext-safety-gate": {
            "PreToolUse": [
                {
                    "matcher": "run_command|replace_file_content|write_to_file",
                    "hooks": [
                        {
                            "type": "command",
                            "command": f"{py_exec} {SCRIPTS_DIR / 'hook_pre_tool.py'}",
                            "timeout": 5,
                        }
                    ],
                }
            ]
        },
        "kortext-cache-invalidation": {
            "PostToolUse": [
                {
                    "matcher": "write_to_file|replace_file_content|multi_replace_file_content",
                    "hooks": [
                        {
                            "type": "command",
                            "command": f"{py_exec} {SCRIPTS_DIR / 'hook_post_tool.py'}",
                            "timeout": 10,
                        }
                    ],
                }
            ]
        },
        "kortext-dag-stop-guard": {
            "Stop": [
                {
                    "type": "command",
                    "command": f"{py_exec} {SCRIPTS_DIR / 'hook_stop.py'}",
                    "timeout": 10,
                }
            ]
        },
    }


def install_plugin():
    home = Path.home()
    plugin_name = "kortext"
    for base_parent in [
        home / ".gemini" / "config" / "plugins",
        home / ".gemini" / "antigravity-cli" / "plugins",
    ]:
        base_plugin_dir = base_parent / plugin_name
        base_plugin_dir.parent.mkdir(parents=True, exist_ok=True)
        if base_plugin_dir.is_symlink() or base_plugin_dir.is_file():
            base_plugin_dir.unlink()
        elif base_plugin_dir.is_dir():
            shutil.rmtree(base_plugin_dir)
        os.symlink(INTEGRATIONS_DIR, base_plugin_dir)
        print(f"📦 Linked {plugin_name} plugin to: {base_plugin_dir}")

    # Backward-compatibility symlink for active session hook runner
    compat_cerebrum_dir = home / ".gemini" / "config" / "plugins" / "cerebrum"
    if not compat_cerebrum_dir.exists() and not compat_cerebrum_dir.is_symlink():
        os.symlink(INTEGRATIONS_DIR, compat_cerebrum_dir)
        print(f"🔗 Maintained backward-compatibility symlink: {compat_cerebrum_dir}")

    # Clean up stale cerebrum plugin from antigravity-cli if present
    stale_cli_cerebrum = home / ".gemini" / "antigravity-cli" / "plugins" / "cerebrum"
    if stale_cli_cerebrum.is_symlink() or stale_cli_cerebrum.is_file():
        stale_cli_cerebrum.unlink()
        print(f"🧹 Cleaned stale cerebrum plugin link: {stale_cli_cerebrum}")
    elif stale_cli_cerebrum.is_dir():
        shutil.rmtree(stale_cli_cerebrum)
        print(f"🧹 Cleaned stale cerebrum plugin directory: {stale_cli_cerebrum}")

    # Generate hooks.json into integrations/antigravity/
    hooks_payload = build_hooks_dict()
    with open(INTEGRATIONS_DIR / "hooks.json", "w", encoding="utf-8") as f:
        json.dump(hooks_payload, f, indent=2)

    # Clean up plugin-level mcp_config.json to prevent plugin namespace duplication
    venv_py = KORTEXT_ROOT / ".venv" / "bin" / "python3"
    py_exec = str(venv_py) if venv_py.is_file() else "python3"

    mcp_config_src = INTEGRATIONS_DIR / "mcp_config.json"
    if mcp_config_src.is_file() or mcp_config_src.is_symlink():
        mcp_config_src.unlink()
        print(f"🧹 Cleaned plugin mcp_config.json: {mcp_config_src}")

    target_plugin_dirs = [
        home / ".gemini" / "config" / "plugins" / "kortext",
        home / ".gemini" / "antigravity-cli" / "plugins" / "kortext",
    ]
    for target_plugin_dir in target_plugin_dirs:
        target_mcp_config = target_plugin_dir / "mcp_config.json"
        if target_mcp_config.is_file() or target_mcp_config.is_symlink():
            target_mcp_config.unlink()
            print(f"🧹 Cleaned plugin mcp_config.json: {target_mcp_config}")

    # Ensure canonical host mcp_config.json has 'kortext' and no duplicate names
    host_mcp_config = home / ".gemini" / "config" / "mcp_config.json"
    if host_mcp_config.is_file():
        try:
            with open(host_mcp_config, "r", encoding="utf-8") as f:
                host_mcp_payload = json.load(f)
        except json.JSONDecodeError:
            host_mcp_payload = {}
    else:
        host_mcp_payload = {}

    if "mcpServers" not in host_mcp_payload or not isinstance(host_mcp_payload["mcpServers"], dict):
        host_mcp_payload["mcpServers"] = {}

    for stale_key in ["cerebrum_kortext", "kortext_kortext"]:
        if stale_key in host_mcp_payload["mcpServers"]:
            del host_mcp_payload["mcpServers"][stale_key]
            print(f"🧹 Removed stale server key: {stale_key}")

    kortext_bin = KORTEXT_ROOT / ".venv" / "bin" / "kortext-server"
    server_cmd = str(kortext_bin) if kortext_bin.is_file() else "kortext-server"

    if "kortext" not in host_mcp_payload["mcpServers"] or not isinstance(host_mcp_payload["mcpServers"]["kortext"], dict):
        host_mcp_payload["mcpServers"]["kortext"] = {
            "command": server_cmd,
            "env": {
                "WORKSPACE_ROOTS": str(KORTEXT_ROOT),
                "LOCAL_LLM_BASE_URL": "http://localhost:8000/v1",
                "EMBED_BASE_URL": "http://localhost:8000/v1",
                "RERANK_BASE_URL": "http://localhost:8000/v1",
                "EMBED_MODEL_NAME": "mlx-community--Qwen3-Embedding-8B-4bit-DWQ",
                "RERANK_MODEL_NAME": "vserifsaglam--Qwen3-Reranker-4B-4bit-MLX",
                "RERANK_TOP_K": "5",
                "RETRIEVE_TOP_K": "30",
                "FALKORDB_HOST": "localhost",
                "FALKORDB_PORT": "6379",
                "FALKORDB_DATABASE": "kortext",
                "QDRANT_COLLECTION": "kortext_codebase",
                "JOURNAL_DIR": str(KORTEXT_ROOT / "journal"),
            },
        }
    else:
        host_mcp_payload["mcpServers"]["kortext"]["command"] = server_cmd

    with open(host_mcp_config, "w", encoding="utf-8") as f:
        json.dump(host_mcp_payload, f, indent=2)
    print(f"🔌 Canonical kortext MCP server verified in: {host_mcp_config}")


    # Synchronize and verify sidecars (integrations/antigravity/sidecars/*)
    sidecars_src = INTEGRATIONS_DIR / "sidecars"
    if sidecars_src.is_dir():
        # Update sidecar manifests to use py_exec
        for sc_dir in sidecars_src.iterdir():
            if sc_dir.is_dir():
                src_sc_json = sc_dir / "sidecar.json"
                if src_sc_json.is_file():
                    with open(src_sc_json, "r", encoding="utf-8") as f:
                        sc_data = json.load(f)
                    sc_data["command"] = py_exec
                    with open(src_sc_json, "w", encoding="utf-8") as f:
                        json.dump(sc_data, f, indent=2)

        for target_plugin_dir in target_plugin_dirs:
            target_sidecars_dir = target_plugin_dir / "sidecars"
            if target_plugin_dir.is_dir() and not target_plugin_dir.is_symlink():
                target_sidecars_dir.mkdir(parents=True, exist_ok=True)
                for sc_dir in sidecars_src.iterdir():
                    if sc_dir.is_dir():
                        dest_sc = target_sidecars_dir / sc_dir.name
                        if dest_sc.exists():
                            shutil.rmtree(dest_sc)
                        shutil.copytree(sc_dir, dest_sc)
            for sc_dir in sidecars_src.iterdir():
                if sc_dir.is_dir():
                    sc_json = target_sidecars_dir / sc_dir.name / "sidecar.json"
                    assert sc_json.is_file(), f"Expected sidecar manifest {sc_json} to exist"
                    with open(sc_json, "r", encoding="utf-8") as f:
                        sc_data = json.load(f)
                        assert "command" in sc_data and "args" in sc_data, f"Invalid sidecar manifest: {sc_json}"
                        assert sc_data["command"] == py_exec, f"Expected sidecar command {py_exec}, got {sc_data['command']}"
                    print(f"🚗 Verified sidecar manifest: {sc_json}")

    # Clean up duplicate skill symlinks in ~/.gemini/config/skills/ so skills are only sourced from the active plugin
    global_skills_dir = home / ".gemini" / "config" / "skills"
    if global_skills_dir.is_dir():
        skills_src = INTEGRATIONS_DIR / "skills"
        if skills_src.is_dir():
            for skill_dir in skills_src.iterdir():
                target_skill = global_skills_dir / skill_dir.name
                if target_skill.is_symlink():
                    target_skill.unlink()
                    print(f"🧹 Cleaned duplicate skill symlink: {skill_dir.name}")
                elif target_skill.is_dir() and not (target_skill / ".git").exists():
                    shutil.rmtree(target_skill)
                    print(f"🧹 Cleaned duplicate skill dir: {skill_dir.name}")

    # Synchronize Rules:
    # 1. Global rules (active across ALL workspaces and directories on workstation)
    plugin_agents_md = INTEGRATIONS_DIR / "rules" / "AGENTS.md"
    global_config_agents_md = home / ".gemini" / "config" / "AGENTS.md"
    global_gemini_agents_md = home / ".gemini" / "AGENTS.md"
    global_rules_dir = home / ".gemini" / "config" / "rules"
    global_rules_dir.mkdir(parents=True, exist_ok=True)

    if plugin_agents_md.is_file():
        shutil.copy2(plugin_agents_md, global_config_agents_md)
        shutil.copy2(plugin_agents_md, global_gemini_agents_md)
        print(f"📋 Installed global rules: {global_config_agents_md} & {global_gemini_agents_md}")

    rules_src = INTEGRATIONS_DIR / "rules"
    if rules_src.is_dir():
        for rule_file in rules_src.glob("*.md"):
            shutil.copy2(rule_file, global_rules_dir / rule_file.name)
        print(f"📋 Installed modular global rules in: {global_rules_dir}")

    # Global compatibility symlinks
    rule_symlinks = [
        (home / ".gemini" / "GEMINI.md", home / ".gemini" / "AGENTS.md"),
        (home / ".gemini" / "config" / "GEMINI.md", home / ".gemini" / "config" / "AGENTS.md"),
        (home / ".gemini" / "antigravity-cli" / "rules", global_rules_dir),
    ]
    for link, target in rule_symlinks:
        link.parent.mkdir(parents=True, exist_ok=True)
        if link.is_symlink() or link.is_file():
            link.unlink()
        elif link.is_dir():
            shutil.rmtree(link)
        link.symlink_to(target)
        print(f"🔗 Linked {link} -> {target}")

    # 2. Workspace rules (local to Cortex workspace)
    workspace_agents_md = CEREBRUM_ROOT / "AGENTS.md"
    if plugin_agents_md.is_file():
        shutil.copy2(plugin_agents_md, workspace_agents_md)
        print(f"📋 Synchronized workspace root rules: {workspace_agents_md}")

    workspace_rules_dir = CEREBRUM_ROOT / ".agents" / "rules"
    workspace_rules_dir.mkdir(parents=True, exist_ok=True)
    if rules_src.is_dir():
        for rule_file in rules_src.glob("*.md"):
            shutil.copy2(rule_file, workspace_rules_dir / rule_file.name)
        print(f"📋 Synchronized workspace rules to: {workspace_rules_dir}")

    # Synchronize Custom Subagents to both workspace .agents/agents and global ~/.gemini/config/agents
    agents_src = INTEGRATIONS_DIR / "agents"
    global_agents_dir = home / ".gemini" / "config" / "agents"
    workspace_agents_dir = CEREBRUM_ROOT / ".agents" / "agents"
    global_agents_dir.mkdir(parents=True, exist_ok=True)
    workspace_agents_dir.mkdir(parents=True, exist_ok=True)

    agent_names = [
        "kortext-architect",
        "kortext-researcher",
        "kortext-code-reviewer",
        "kortext-task-runner",
    ]

    # Clean up stale cerebrum-* agent folders and files in destination directories
    for target_dir in [global_agents_dir, workspace_agents_dir]:
        for stale_file in target_dir.glob("cerebrum-*.md"):
            if stale_file.is_file() or stale_file.is_symlink():
                stale_file.unlink()
                print(f"🧹 Cleaned up stale agent file: {stale_file}")
        for stale_folder in target_dir.glob("cerebrum-*"):
            if stale_folder.is_dir():
                shutil.rmtree(stale_folder)
                print(f"🧹 Cleaned up stale agent directory: {stale_folder}")

    for name in agent_names:
        src_md = agents_src / f"{name}.md"
        src_dir_md = agents_src / name / "agent.md"
        agent_content_src = src_dir_md if src_dir_md.is_file() else src_md

        if agent_content_src.is_file():
            # 1. Global config: both <name>/agent.md and <name>.md
            global_subagent_folder = global_agents_dir / name
            global_subagent_folder.mkdir(parents=True, exist_ok=True)
            for target_dst in [
                global_subagent_folder / "agent.md",
                global_agents_dir / f"{name}.md",
            ]:
                if target_dst.is_symlink() or target_dst.is_file():
                    target_dst.unlink()
                shutil.copy2(agent_content_src, target_dst)

            # 2. Workspace .agents/agents: both <name>/agent.md and <name>.md
            ws_subagent_folder = workspace_agents_dir / name
            ws_subagent_folder.mkdir(parents=True, exist_ok=True)
            for target_dst in [
                ws_subagent_folder / "agent.md",
                workspace_agents_dir / f"{name}.md",
            ]:
                if target_dst.is_symlink() or target_dst.is_file():
                    target_dst.unlink()
                shutil.copy2(agent_content_src, target_dst)

            print(f"🤖 Installed subagent: {name}")

    # Synchronize agents.json discovery manifests
    agents_json_payload = {
        "entries": [
            {"path": "integrations/antigravity/agents"},
            {"path": ".agents/agents"}
        ]
    }
    with open(CEREBRUM_ROOT / ".agents" / "agents.json", "w", encoding="utf-8") as f:
        json.dump(agents_json_payload, f, indent=2)

    global_agents_json_payload = {
        "entries": [
            {"path": str(global_agents_dir)}
        ]
    }
    with open(home / ".gemini" / "config" / "agents.json", "w", encoding="utf-8") as f:
        json.dump(global_agents_json_payload, f, indent=2)

    print("📄 Synchronized agents.json discovery manifests")

    # Make hook scripts executable
    for script in SCRIPTS_DIR.glob("*.py"):
        st = os.stat(script)
        os.chmod(script, st.st_mode | stat.S_IEXEC)


def install_all():
    home = Path.home()
    for storage_name in [".kortext", ".cerebrum"]:
        storage_home = home / storage_name
        for d in ["bin", "run", "logs", "config", "data/falkordb", "qdrant"]:
            (storage_home / d).mkdir(parents=True, exist_ok=True)
        print(f"📦 Provisioned storage directories in {storage_home}")

    # Verify native binary
    cerebrum_home = home / ".cerebrum"
    bin_so = cerebrum_home / "bin" / "falkordb.so"
    if not bin_so.is_file():
        import subprocess
        build_script = KORTEXT_ROOT / "scripts" / "build_falkordb_native.sh"
        subprocess.run(["bash", str(build_script)], check=True)

    # Copy config
    conf_src = cerebrum_home / "config" / "falkordb.conf"
    if not conf_src.exists():
        template_conf = KORTEXT_ROOT / "config" / "falkordb.conf"
        if template_conf.exists():
            shutil.copy(template_conf, conf_src)

    # LaunchAgents on Darwin
    if os.uname().sysname == "Darwin":
        launch_dir = home / "Library" / "LaunchAgents"
        launch_dir.mkdir(parents=True, exist_ok=True)
        daemons_dir = INTEGRATIONS_DIR / "daemons"
        if daemons_dir.is_dir():
            for plist in daemons_dir.glob("*.plist"):
                target_plist = launch_dir / plist.name
                shutil.copy(plist, target_plist)
                print(f"📦 Installed LaunchAgent: {plist.name}")

    install_plugin()


def main():
    import sys
    print(f"🧠 Installing Kortext Antigravity Plugin from {KORTEXT_ROOT}...")
    if "--all" in sys.argv:
        install_all()
    else:
        install_plugin()
    print("🎉 Kortext Antigravity Plugin installed and synchronized dynamically!")


if __name__ == "__main__":
    main()
