"""
Tests verifying that all Cerebrum hooks strictly obey the Antigravity stdin/stdout JSON contract.
"""

import json
import subprocess
import sys
from pathlib import Path

HOOKS_DIR = Path(__file__).resolve().parent.parent / "scripts" / "hooks"


class TestAntigravityHooksContract:
    def test_pre_invoke_hook_turn0_contract(self):
        script = HOOKS_DIR / "hook_pre_invoke.py"
        if not script.is_file():
            return

        payload = {
            "invocationNum": 0,
            "initialNumSteps": 0,
            "conversationId": "test-uuid-1234",
            "workspacePaths": ["/workspace"],
            "transcriptPath": "/tmp/transcript.jsonl",
            "artifactDirectoryPath": "/tmp",
            "modelName": "gemini-3.8-flash"
        }

        proc = subprocess.run(
            [sys.executable, str(script)],
            input=json.dumps(payload),
            capture_output=True,
            text=True
        )

        assert proc.returncode == 0
        res = json.loads(proc.stdout)
        # PreInvocation output contract must be {"injectSteps": [...]} or {}
        assert "injectSteps" in res
        assert len(res["injectSteps"]) > 0
        assert "ephemeralMessage" in res["injectSteps"][0]

    def test_stop_hook_contract(self):
        script = HOOKS_DIR / "hook_stop.py"
        if not script.is_file():
            return

        payload = {
            "executionNum": 1,
            "terminationReason": "model_stop",
            "error": "",
            "fullyIdle": True,
            "conversationId": "test-uuid-5678",
            "workspacePaths": ["/workspace"],
            "transcriptPath": "/nonexistent/transcript.jsonl",
            "artifactDirectoryPath": "/tmp",
            "modelName": "gemini-3.8-flash"
        }

        proc = subprocess.run(
            [sys.executable, str(script)],
            input=json.dumps(payload),
            capture_output=True,
            text=True
        )

        assert proc.returncode == 0
        res = json.loads(proc.stdout)
        # Stop hook output contract requires 'decision'
        assert "decision" in res
        assert res["decision"] in ("stop", "continue")
