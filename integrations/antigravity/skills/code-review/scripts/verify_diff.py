#!/usr/bin/env python3
"""
Black-box verification helper for the `code-review` skill.
Audits staged or working-tree git diffs for:
  1. File line-count ceiling (>800 lines warning, >1000 lines block)
  2. Prohibited `unittest.mock` usage in production modules
  3. Swallowed `except Exception: pass` silent failures
  4. Leftover `[DEBUG-` probes or hardcoded secrets
Usage:
  python3 verify_diff.py [--base HEAD] [--strict]
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import re
import subprocess
import sys
from typing import Any, Dict, List

SECRET_RE = re.compile(r"(sk-[a-zA-Z0-9_\-]{20,}|ghp_[a-zA-Z0-9]{36,}|AKIA[0-9A-Z]{16})")
SILENT_PASS_RE = re.compile(r"^\+\s*pass\s*$")
EXCEPT_BROAD_RE = re.compile(r"^\+\s*except\s+Exception(?:\s+as\s+\w+)?\s*:\s*$")


def analyze_diff(base: str = "HEAD", strict: bool = False) -> Dict[str, Any]:
    cmd = ["git", "diff", "--unified=3", base]
    proc = subprocess.run(cmd, capture_output=True, text=True, check=False)
    diff_text = proc.stdout or ""

    files_cmd = ["git", "diff", "--name-only", base]
    files_proc = subprocess.run(files_cmd, capture_output=True, text=True, check=False)
    changed_files = [ln.strip() for ln in (files_proc.stdout or "").splitlines() if ln.strip()]

    findings: List[Dict[str, Any]] = []
    for fp in changed_files:
        p = Path(fp)
        if not p.is_file():
            continue
        is_test = "tests" in p.parts or p.name.startswith("test_") or p.name == "conftest.py"
        lines = p.read_text(encoding="utf-8", errors="ignore").splitlines()
        line_count = len(lines)
        if line_count > 1000:
            findings.append({
                "severity": "CRITICAL",
                "file": fp,
                "issue": f"File exceeds 1,000-line hard ceiling ({line_count} lines).",
            })
        elif strict and line_count > 800:
            findings.append({
                "severity": "HIGH",
                "file": fp,
                "issue": f"File exceeds 800-line strict threshold ({line_count} lines).",
            })

        if not is_test and p.suffix == ".py":
            text = "\n".join(lines)
            if "unittest.mock" in text:
                findings.append({
                    "severity": "CRITICAL",
                    "file": fp,
                    "issue": "Production module imports unittest.mock.",
                })

    current_file = ""
    prev_was_broad_except = False
    for line in diff_text.splitlines():
        if line.startswith("+++ b/"):
            current_file = line[6:].strip()
            prev_was_broad_except = False
            continue
        if not line.startswith("+") or line.startswith("+++"):
            if not line.startswith(" "):
                prev_was_broad_except = False
            continue
        if "[DEBUG-" in line:
            findings.append({
                "severity": "HIGH",
                "file": current_file,
                "issue": f"Leftover tagged debug probe: {line[1:].strip()[:80]}",
            })
        if SECRET_RE.search(line) and "tests" not in Path(current_file).parts:
            findings.append({
                "severity": "CRITICAL",
                "file": current_file,
                "issue": "Potential hardcoded secret/API key in added line.",
            })
        if EXCEPT_BROAD_RE.match(line):
            prev_was_broad_except = True
        elif prev_was_broad_except and SILENT_PASS_RE.match(line):
            findings.append({
                "severity": "HIGH",
                "file": current_file,
                "issue": "Silent `except Exception: pass` block added in diff.",
            })
            prev_was_broad_except = False
        else:
            prev_was_broad_except = False

    verdict = "BLOCK" if any(f["severity"] in ("CRITICAL", "HIGH") for f in findings) else "APPROVE"
    return {
        "verdict": verdict,
        "changed_files_count": len(changed_files),
        "changed_files": changed_files,
        "findings_count": len(findings),
        "findings": findings,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Verify git diff against Kortext 6-Axis & Thermo-Nuclear gates.")
    parser.add_argument("--base", default="HEAD", help="Git ref to diff against (default: HEAD)")
    parser.add_argument("--strict", action="store_true", help="Enable --strict / Thermo-Nuclear thresholds")
    args = parser.parse_args()
    report = analyze_diff(base=args.base, strict=args.strict)
    print(json.dumps(report, indent=2))
    sys.exit(1 if report["verdict"] == "BLOCK" else 0)


if __name__ == "__main__":
    main()
