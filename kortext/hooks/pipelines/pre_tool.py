"""
Pre-tool interceptor pipeline and security/invariant guards for Antigravity hooks.
"""

from __future__ import annotations

import logging
import os
import re
import sys
from pathlib import Path
from types import MappingProxyType
from typing import Any, List, Optional, Sequence

from kortext.hooks.context import HookContext
from kortext.hooks.types import InterceptorResult

logger = logging.getLogger("kortext.hooks.pipelines.pre_tool")

CORE_ARCHITECTURAL_FILES = frozenset({
    "server.py",
    "graph.py",
    "health.py",
    "falkordb_client.py",
    "_qdrant.py",
    "dream.py",
    "invariants.py",
    "tracker.py",
    "sanitizer.py",
    "engine.py",
    "driver.py",
})

DANGEROUS_PATTERNS = [
    re.compile(r"\brm\s+-[a-zA-Z]*r[a-zA-Z]*f\s+[/~]", re.IGNORECASE),
    re.compile(r"\bformat\s+c:", re.IGNORECASE),
    re.compile(r">\s*~?/?(?:\.kortext|\.cerebrum)/data/", re.IGNORECASE),
    re.compile(r"\bcp\s+.*~?/?(?:\.kortext|\.cerebrum)/data/", re.IGNORECASE),
    re.compile(r"\bmv\s+.*~?/?(?:\.kortext|\.cerebrum)/data/", re.IGNORECASE),
    re.compile(r"\bgit\s+reset\s+--hard\b", re.IGNORECASE),
    re.compile(r":\(\)\s*\{\s*:\|:&\s*\};:"),
]

SECRET_PATTERNS = [
    re.compile(r"\bsk-[a-zA-Z0-9_\-]{20,}\b"),
    re.compile(r"\bghp_[a-zA-Z0-9]{36,}\b"),
    re.compile(r"\bgithub_pat_[a-zA-Z0-9]{22}_[a-zA-Z0-9]{59}\b"),
    re.compile(r"\bAKIA[0-9A-Z]{16}\b"),
    re.compile(r"-----BEGIN (?:RSA|EC|DSA|OPENSSH|PGP) PRIVATE KEY-----"),
    re.compile(r"\bxox[baprs]-[0-9a-zA-Z]{10,48}\b"),
]


class FastMCPLockGuard:
    """
    Guards against embedded Qdrant direct instantiation.
    Enforces the Sole Custodian model to prevent SQLite/RocksDB exclusive file lock collisions.
    """

    def check(self, context: HookContext) -> InterceptorResult:
        if context.tool_name != "run_command":
            return InterceptorResult.allow()

        cmd = context.command_line
        if not cmd:
            return InterceptorResult.allow()

        # Check for python code calling QdrantClient with path=
        if re.search(r"qdrant_client.*path\s*=", cmd, re.IGNORECASE) or re.search(
            r"QdrantClient\s*\([^)]*path\s*=", cmd, re.IGNORECASE
        ):
            reason = (
                "[FastMCPLockGuard] Execution blocked: Direct embedded QdrantClient instantiation with 'path=' "
                "is strictly prohibited. Violates Sole Custodian invariant and causes exclusive lock contention "
                "(sqlite3.OperationalError: database is locked). Use FastMCP server tools instead."
            )
            return InterceptorResult.deny(reason=reason)

        return InterceptorResult.allow()


class AntiRipgrepGate:
    """
    Enforces the Anti-Ripgrep Mandate.
    Denies broad rg/grep scans for symbols and redirects agents to seek_symbol.
    """

    PERMITTED_EXCEPTIONS = frozenset({"pytest", "journal", "log", "curl"})

    def check(self, context: HookContext) -> InterceptorResult:
        if context.tool_name != "run_command":
            return InterceptorResult.allow()

        cmd = context.command_line
        if not cmd:
            return InterceptorResult.allow()

        lower_cmd = cmd.lower()
        if not (lower_cmd.startswith("rg ") or " rg " in lower_cmd or "grep " in lower_cmd):
            return InterceptorResult.allow()

        # Check permitted exceptions
        if any(exc in lower_cmd for exc in self.PERMITTED_EXCEPTIONS):
            return InterceptorResult.allow()

        # Check if grep/rg targets a single existing file (permitted narrow exception)
        parts = cmd.split()
        if len(parts) >= 3 and not any(flag in cmd for flag in (" -r", " -R", " --recursive")):
            last_arg = parts[-1].strip("'\"")
            if os.path.isfile(last_arg):
                return InterceptorResult.allow()

        # If searching for code definitions or broad scan across workspace
        symbol_indicators = ("def ", "class ", "fn ", "function ", "interface ", "struct ", "type ")
        is_symbol_search = any(ind in lower_cmd for ind in symbol_indicators)
        is_broad_rg = lower_cmd.startswith("rg ") or " rg " in lower_cmd

        if is_symbol_search or is_broad_rg:
            reason = (
                "🛑 [AntiRipgrepGate] Broad symbol search via rg/grep is prohibited. "
                "Use `seek_symbol(symbol_name='<symbol>')` for deterministic AST point lookup (<2ms, <150 tokens) "
                "or `trace_symbol_impact` to preserve context tokens and prevent context degradation."
            )
            return InterceptorResult.deny(reason=reason)

        return InterceptorResult.allow()


class CommandSafetyGuard:
    """
    Intercepts dangerous, destructive, or unauthorized direct substrate writes.
    """

    def check(self, context: HookContext) -> InterceptorResult:
        if context.tool_name != "run_command":
            return InterceptorResult.allow()

        cmd = context.command_line
        if not cmd:
            return InterceptorResult.allow()

        for pattern in DANGEROUS_PATTERNS:
            if pattern.search(cmd):
                matched = pattern.pattern
                reason = (
                    f"🛑 [CommandSafetyGuard] Forbidden destructive pattern detected: '{matched}'. "
                    "Command execution has been blocked."
                )
                return InterceptorResult.deny(reason=reason)

        return InterceptorResult.allow()


class SecretLeakGuard:
    """
    Scans command lines and file modifications for high-entropy secrets and API tokens.
    """

    def check(self, context: HookContext) -> InterceptorResult:
        # Check command line
        if context.tool_name == "run_command":
            cmd = context.command_line
            if cmd:
                for pattern in SECRET_PATTERNS:
                    if pattern.search(cmd):
                        return InterceptorResult.deny(
                            reason="🛑 [SecretLeakGuard] Potential secret/credential leak detected in command line. "
                            "Load secrets from environment variables instead."
                        )

        # Check file edit payloads
        if context.tool_name in ("write_to_file", "replace_file_content", "multi_replace_file_content"):
            args = context.tool_args
            for field_name in ("CodeContent", "ReplacementContent", "code", "content"):
                content = str(args.get(field_name, ""))
                if content:
                    for pattern in SECRET_PATTERNS:
                        if pattern.search(content):
                            return InterceptorResult.deny(
                                reason=f"🛑 [SecretLeakGuard] Potential secret/API key leak detected in '{field_name}'. "
                                "Never commit credentials or tokens into source code."
                            )

        return InterceptorResult.allow()


class BlastRadiusGuard:
    """
    Audits modifications to core architectural files and warns if trace_symbol_impact was not run.
    """

    def check(self, context: HookContext) -> InterceptorResult:
        if context.tool_name not in ("write_to_file", "replace_file_content", "multi_replace_file_content"):
            return InterceptorResult.allow()

        target_file = context.target_file
        if not target_file:
            return InterceptorResult.allow()

        file_name = Path(target_file).name
        if file_name not in CORE_ARCHITECTURAL_FILES:
            return InterceptorResult.allow()

        # Check transcript if trace_symbol_impact was called
        steps = context.read_transcript_steps()
        traced = False
        for step in steps:
            for tc in step.get("tool_calls", ()):
                if isinstance(tc, (dict, MappingProxyType)):
                    name = str(tc.get("name") or tc.get("tool_name") or "")
                    if "trace_symbol_impact" in name:
                        traced = True
                        break
            if traced:
                break

        if not traced:
            msg = (
                f"[BlastRadiusGuard] ℹ️ Modifying core architectural file '{file_name}' without prior "
                "trace_symbol_impact analysis. Consider running trace_symbol_impact to verify symbol dependencies."
            )
            print(msg, file=sys.stderr)
            return InterceptorResult.allow(
                reason="Advisory: Core file modification without prior trace_symbol_impact.",
                data=MappingProxyType({"advisory": msg, "target_file": target_file}),
            )

        return InterceptorResult.allow()


class PreToolPipeline:
    """Dispatches PreToolUse interceptors sequentially."""

    def __init__(self, guards: Optional[Sequence[Any]] = None):
        self.guards = tuple(guards) if guards is not None else (
            FastMCPLockGuard(),
            AntiRipgrepGate(),
            CommandSafetyGuard(),
            SecretLeakGuard(),
            BlastRadiusGuard(),
        )

    def execute(self, context: HookContext) -> InterceptorResult:
        for guard in self.guards:
            try:
                res = guard.check(context)
                if res.decision == "deny":
                    return res
            except Exception as e:
                logger.debug("Guard %s failed with exception: %s", type(guard).__name__, e)
                # Fail-safe: do not crash background hooks
                continue

        return InterceptorResult.allow()
