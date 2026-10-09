"""
Pre-invocation pipeline: Substrate health probing, Task DAG notifications,
context budgeting, and ambient Turn 0 invariant injection.
"""

from __future__ import annotations

import logging
import os
import re
import socket
import sys
import urllib.request
from pathlib import Path
from types import MappingProxyType
from typing import Any, Dict, List, Optional, Sequence

from kortext._home import get_kortext_home
from kortext.hooks.context import HookContext
from kortext.hooks.types import InterceptorResult

logger = logging.getLogger("kortext.hooks.pipelines.pre_invoke")


def _check_unix_socket(sock_path: Path, timeout_sec: float = 0.05) -> bool:
    """Non-blocking connect probe for Unix domain sockets."""
    if not sock_path.is_socket():
        return False
    try:
        with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as sock:
            sock.settimeout(timeout_sec)
            sock.connect(str(sock_path))
            return True
    except Exception:
        return False


def _check_tcp(host: str, port: int, timeout_sec: float = 0.05) -> bool:
    """Non-blocking TCP socket connect probe."""
    try:
        with socket.create_connection((host, port), timeout=timeout_sec):
            return True
    except Exception:
        return False


def _check_http(host: str, port: int, path: str = "/healthz", timeout_sec: float = 0.05) -> bool:
    """Non-blocking HTTP GET probe."""
    try:
        req = urllib.request.Request(f"http://{host}:{port}{path}", method="GET")
        with urllib.request.urlopen(req, timeout=timeout_sec) as resp:
            return resp.status < 500
    except Exception:
        return False


class SubstrateHealthProbe:
    """
    Non-blocking socket probe (<2ms) verifying FalkorDB (UDS/TCP) and Qdrant (HTTP).
    """

    def __init__(self, timeout_sec: float = 0.05):
        self.timeout_sec = timeout_sec

    def check(self, context: HookContext) -> InterceptorResult:
        home = get_kortext_home()
        falkor_sock = home / "run" / "falkordb.sock"
        legacy_sock = Path.home() / ".cerebrum" / "run" / "falkordb.sock"

        falkor_ok = False
        if _check_unix_socket(falkor_sock, self.timeout_sec):
            falkor_ok = True
        elif _check_unix_socket(legacy_sock, self.timeout_sec):
            falkor_ok = True
        elif _check_tcp("127.0.0.1", 6379, self.timeout_sec):
            falkor_ok = True

        qdrant_ok = _check_http("127.0.0.1", 6333, path="/healthz", timeout_sec=self.timeout_sec)
        if not qdrant_ok:
            # Fallback check for root endpoint
            qdrant_ok = _check_tcp("127.0.0.1", 6333, self.timeout_sec)

        down_services: List[str] = []
        if not falkor_ok:
            down_services.append("FalkorDB")
        if not qdrant_ok:
            down_services.append("Qdrant")

        data: Dict[str, Any] = {
            "falkordb": falkor_ok,
            "qdrant": qdrant_ok,
            "down_services": down_services,
        }

        if down_services:
            msg = (
                f"⚠️ [Kortext Health Alert] Offline services detected: {', '.join(down_services)}. "
                "Run `kortext start` to bring memory and graph substrates online."
            )
            print(msg, file=sys.stderr)
            data["health_alert"] = msg

        return InterceptorResult.allow(data=MappingProxyType(data))


class FrontierDAGNotifier:
    """
    Checks manage_tasks / TaskDAGTracker for unblocked ready tasks and notifies agent.
    """

    def process(self, context: HookContext) -> InterceptorResult:
        try:
            from kortext.tasks.tracker import TaskDAGTracker

            tracker = TaskDAGTracker()
            ready_tasks = tracker.get_ready_tasks()
            if ready_tasks:
                task_summary = [f"{t.get('id')}: {t.get('title')}" for t in ready_tasks[:3]]
                msg = f"📋 [Frontier DAG Notice] Unblocked ready tasks awaiting execution: {', '.join(task_summary)}"
                return InterceptorResult.allow(
                    data=MappingProxyType({
                        "ready_tasks": tuple(ready_tasks),
                        "dag_notice": msg,
                    })
                )
        except Exception as e:
            logger.debug("FrontierDAGNotifier check bypassed: %s", e)

        return InterceptorResult.allow()


class ContextBudgetAdvisor:
    """
    Checks transcript steps and suggests subagent delegation for complex sessions.
    """

    def __init__(self, warning_threshold_steps: int = 15):
        self.warning_threshold_steps = warning_threshold_steps

    def process(self, context: HookContext) -> InterceptorResult:
        steps = context.read_transcript_steps()
        if len(steps) >= self.warning_threshold_steps:
            msg = (
                f"💡 [Context Budget Advisor] Session transcript contains {len(steps)} steps. "
                "To prevent context dilution and preserve token budget, consider decomposing remaining "
                "multi-file tasks and delegating them to subagents via Task DAG."
            )
            return InterceptorResult.allow(
                data=MappingProxyType({
                    "budget_warning": msg,
                    "step_count": len(steps),
                })
            )

        return InterceptorResult.allow()


class InvariantInjector:
    """
    Injects ambient architectural directives and invariants on Turn 0.
    """

    def __init__(self, journal_dir: Optional[Path] = None):
        self.journal_dir = journal_dir or (Path(__file__).resolve().parent.parent.parent.parent / "journal")

    def process(self, context: HookContext) -> InterceptorResult:
        if not context.is_first_turn:
            return InterceptorResult.allow()

        inv_file = self.journal_dir / "invariants.md"
        invariants: List[str] = []
        if inv_file.is_file():
            try:
                text = inv_file.read_text(encoding="utf-8")
                pattern = re.compile(
                    r"###\s+Invariant\s+\[(.*?)\]\s*\n\*\*Rule:\*\*\s*(.*?)(?=\n\*\*Rationale:|\n###|\Z)",
                    re.DOTALL,
                )
                for match in pattern.finditer(text):
                    topic = match.group(1).strip()
                    rule = match.group(2).strip().replace("\n", " ")
                    invariants.append(f"• **[{topic}]**: {rule}")
                    if len(invariants) >= 3:
                        break
            except Exception as e:
                logger.debug("Failed reading invariants file: %s", e)

        inv_str = "\n".join(invariants) if invariants else "• Ambient invariants synchronized."

        ambient_message = (
            "🧠 [Kortext Cognitive OS Initialized]\n"
            "Active Protocols:\n"
            "1. ANTI-RIPGREP MANDATE: Do NOT run `rg` or `grep_search` to find symbols. Use `seek_symbol`.\n"
            "2. DELEGATION MANDATE: For multi-file changes (Complexity >= 4), initialize DAG via `manage_tasks`.\n"
            "3. PERSISTENCE MANDATE: Record outcomes via `record_system_outcome` before session stop.\n\n"
            f"Active Invariants:\n{inv_str}"
        )

        inject_steps = ({"ephemeralMessage": ambient_message},)
        return InterceptorResult.allow(
            data=MappingProxyType({"injectSteps": inject_steps})
        )


class PreInvokePipeline:
    """Dispatches PreInvocation interceptors and merges injected steps."""

    def __init__(self, interceptors: Optional[Sequence[Any]] = None):
        self.interceptors = tuple(interceptors) if interceptors is not None else (
            SubstrateHealthProbe(),
            FrontierDAGNotifier(),
            ContextBudgetAdvisor(),
            InvariantInjector(),
        )

    def execute(self, context: HookContext) -> InterceptorResult:
        merged_data: Dict[str, Any] = {}
        for interceptor in self.interceptors:
            try:
                if hasattr(interceptor, "process"):
                    res = interceptor.process(context)
                elif hasattr(interceptor, "check"):
                    res = interceptor.check(context)
                else:
                    continue

                if res.data:
                    for k, v in res.data.items():
                        merged_data[k] = v
            except Exception as e:
                logger.debug("PreInvoke interceptor %s failed: %s", type(interceptor).__name__, e)
                continue

        return InterceptorResult.allow(data=MappingProxyType(merged_data))
