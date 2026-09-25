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

CEREBRUM_ROOT = Path(__file__).resolve().parent.parent
INTEGRATIONS_DIR = CEREBRUM_ROOT / "integrations" / "antigravity"
SCRIPTS_DIR = CEREBRUM_ROOT / "scripts" / "hooks"


def build_hooks_dict() -> dict:
    venv_py = CEREBRUM_ROOT / ".venv" / "bin" / "python3"
    py_exec = str(venv_py) if venv_py.is_file() else "python3"
    return {
        "cerebrum-ambient-grounding": {
            "PreInvocation": [
                {
                    "type": "command",
                    "command": f"{py_exec} {SCRIPTS_DIR / 'hook_pre_invoke.py'}",
                    "timeout": 15,
                }
            ]
        },
        "cerebrum-safety-gate": {
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
        "cerebrum-cache-invalidation": {
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
        "cerebrum-dag-stop-guard": {
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
    dest_dir = home / ".gemini" / "config" / "plugins" / "cerebrum"
    dest_dir.parent.mkdir(parents=True, exist_ok=True)

    if dest_dir.is_symlink() or dest_dir.is_file():
        dest_dir.unlink()
    elif dest_dir.is_dir():
        shutil.rmtree(dest_dir)

    os.symlink(INTEGRATIONS_DIR, dest_dir)
    print(f"📦 Linked Cerebrum plugin to: {dest_dir}")

    # Generate hooks.json into integrations/antigravity/
    hooks_payload = build_hooks_dict()
    with open(INTEGRATIONS_DIR / "hooks.json", "w", encoding="utf-8") as f:
        json.dump(hooks_payload, f, indent=2)

    # Link skills to global config
    skills_src = INTEGRATIONS_DIR / "skills"
    if skills_src.is_dir():
        for skill_dir in skills_src.iterdir():
            if skill_dir.is_dir():
                target_skill = home / ".gemini" / "config" / "skills" / skill_dir.name
                if target_skill.is_symlink():
                    target_skill.unlink()
                elif target_skill.is_dir():
                    shutil.rmtree(target_skill)
                os.symlink(skill_dir, target_skill)
                print(f"📦 Linked skill: {skill_dir.name}")

    # Make hook scripts executable
    for script in SCRIPTS_DIR.glob("*.py"):
        st = os.stat(script)
        os.chmod(script, st.st_mode | stat.S_IEXEC)


def install_all():
    home = Path.home()
    cerebrum_home = home / ".cerebrum"
    for d in ["bin", "run", "logs", "config", "data/falkordb", "qdrant"]:
        (cerebrum_home / d).mkdir(parents=True, exist_ok=True)
    print(f"📦 Provisioned Cerebrum storage directories in {cerebrum_home}")

    # Verify native binary
    bin_so = cerebrum_home / "bin" / "falkordb.so"
    if not bin_so.is_file():
        import subprocess
        build_script = CEREBRUM_ROOT / "scripts" / "build_falkordb_native.sh"
        subprocess.run(["bash", str(build_script)], check=True)

    # Copy config
    conf_src = cerebrum_home / "config" / "falkordb.conf"
    if not conf_src.exists():
        template_conf = CEREBRUM_ROOT / "config" / "falkordb.conf"
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
    print(f"🧠 Installing Cerebrum Antigravity Plugin from {CEREBRUM_ROOT}...")
    if "--all" in sys.argv:
        install_all()
    else:
        install_plugin()
    print("🎉 Cerebrum Antigravity Plugin installed and synchronized dynamically!")


if __name__ == "__main__":
    main()
