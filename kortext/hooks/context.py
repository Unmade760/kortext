"""
Immutable HookContext dataclass and stdin parsing for Antigravity Lifecycle Hooks.
"""

from __future__ import annotations

import json
import logging
import os
import sys
from dataclasses import dataclass, field
from pathlib import Path
from types import MappingProxyType
from typing import Any, Dict, List, Mapping, Optional, Tuple

logger = logging.getLogger("kortext.hooks.context")


def _freeze_dict(d: Optional[Mapping[str, Any]]) -> MappingProxyType:
    """Recursively converts a mapping into an immutable MappingProxyType."""
    if not d:
        return MappingProxyType({})
    frozen: Dict[str, Any] = {}
    for k, v in d.items():
        if isinstance(v, dict):
            frozen[k] = _freeze_dict(v)
        elif isinstance(v, list):
            frozen[k] = tuple(_freeze_dict(item) if isinstance(item, dict) else item for item in v)
        else:
            frozen[k] = v
    return MappingProxyType(frozen)


@dataclass(frozen=True)
class HookContext:
    """
    Immutable representation of Antigravity lifecycle hook execution context.
    Parsed from stdin JSON payload.
    """

    raw_payload: Mapping[str, Any] = field(default_factory=lambda: MappingProxyType({}))
    event: str = ""
    tool_call: Mapping[str, Any] = field(default_factory=lambda: MappingProxyType({}))
    cwd: str = ""
    transcript_path: str = ""
    session_id: str = ""
    turn_index: int = 0
    tool_result: Mapping[str, Any] = field(default_factory=lambda: MappingProxyType({}))
    termination_reason: str = ""
    fully_idle: bool = True

    @property
    def tool_name(self) -> str:
        """Returns the name of the tool being executed, if any."""
        name = self.tool_call.get("name") or self.tool_call.get("tool_name") or ""
        return str(name)

    @property
    def tool_args(self) -> Mapping[str, Any]:
        """Returns read-only mapping of tool call arguments."""
        args = self.tool_call.get("args") or self.tool_call.get("arguments") or {}
        if isinstance(args, MappingProxyType):
            return args
        if isinstance(args, dict):
            return _freeze_dict(args)
        return MappingProxyType({})

    @property
    def command_line(self) -> str:
        """Returns the command line string for run_command tool calls."""
        args = self.tool_args
        cmd = args.get("CommandLine") or args.get("command") or args.get("cmd") or ""
        return str(cmd).strip()

    @property
    def target_file(self) -> str:
        """Returns the target file path for file modification tools."""
        args = self.tool_args
        target = (
            args.get("TargetFile")
            or args.get("target_file")
            or args.get("AbsolutePath")
            or args.get("path")
            or args.get("file_path")
            or ""
        )
        return str(target).strip()

    @property
    def is_first_turn(self) -> bool:
        """Indicates whether this is the initial turn (Turn 0) of the session."""
        return self.turn_index == 0

    def read_transcript_steps(self) -> Tuple[Mapping[str, Any], ...]:
        """
        Reads steps from transcript.jsonl.
        If an entry has 'truncated_fields', resolves from transcript_full.jsonl.
        Returns an immutable tuple of step mappings.
        """
        if not self.transcript_path or not os.path.isfile(self.transcript_path):
            return ()

        full_path = Path(self.transcript_path).parent / "transcript_full.jsonl"
        full_steps_by_id: Dict[str, Mapping[str, Any]] = {}
        full_steps_by_index: List[Mapping[str, Any]] = []

        if full_path.is_file():
            try:
                with open(full_path, "r", encoding="utf-8", errors="replace") as f_full:
                    for line in f_full:
                        line = line.strip()
                        if not line:
                            continue
                        try:
                            s = json.loads(line)
                            if isinstance(s, dict):
                                frozen_s = _freeze_dict(s)
                                full_steps_by_index.append(frozen_s)
                                sid = s.get("id") or s.get("step_id")
                                if sid is not None:
                                    full_steps_by_id[str(sid)] = frozen_s
                        except Exception:
                            continue
            except Exception as e:
                logger.debug("Failed to read transcript_full.jsonl: %s", e)

        steps: List[Mapping[str, Any]] = []
        try:
            with open(self.transcript_path, "r", encoding="utf-8", errors="replace") as f:
                for line_idx, line in enumerate(f):
                    line = line.strip()
                    if not line:
                        continue
                    try:
                        step_data = json.loads(line)
                    except Exception:
                        continue

                    if not isinstance(step_data, dict):
                        continue

                    if step_data.get("truncated_fields"):
                        resolved_step = None
                        sid = step_data.get("id") or step_data.get("step_id")
                        if sid is not None and str(sid) in full_steps_by_id:
                            resolved_step = full_steps_by_id[str(sid)]
                        elif line_idx < len(full_steps_by_index):
                            resolved_step = full_steps_by_index[line_idx]

                        if resolved_step:
                            steps.append(resolved_step)
                            continue

                    steps.append(_freeze_dict(step_data))
        except Exception as e:
            logger.debug("Failed reading transcript steps from %s: %s", self.transcript_path, e)
            return ()

        return tuple(steps)

    @classmethod
    def from_stdin(
        cls,
        raw_text: Optional[str] = None,
        event: str = "",
    ) -> "HookContext":
        """
        Parses HookContext from raw text (or sys.stdin) with safe fallback.
        Never throws on empty or invalid input.
        """
        if raw_text is None:
            try:
                raw_text = sys.stdin.read().strip()
            except Exception as e:
                logger.debug("Error reading sys.stdin: %s", e)
                raw_text = ""

        if not raw_text or not raw_text.strip():
            return cls(event=event)

        try:
            parsed = json.loads(raw_text)
            if not isinstance(parsed, dict):
                return cls(event=event)
        except Exception as e:
            logger.debug("Failed to decode JSON from stdin: %s", e)
            return cls(event=event)

        tool_call_data = parsed.get("toolCall") or parsed.get("tool_call") or {}
        if not isinstance(tool_call_data, dict):
            tool_call_data = {}

        tool_result_data = parsed.get("toolResult") or parsed.get("tool_result") or {}
        if not isinstance(tool_result_data, dict):
            tool_result_data = {}

        event_name = event or str(parsed.get("event") or "")

        turn_index = 0
        for turn_key in ("invocationNum", "executionNum", "turnIndex", "turn_index"):
            if turn_key in parsed:
                try:
                    turn_index = int(parsed[turn_key])
                    break
                except (ValueError, TypeError):
                    pass

        return cls(
            raw_payload=_freeze_dict(parsed),
            event=event_name,
            tool_call=_freeze_dict(tool_call_data),
            cwd=str(parsed.get("cwd") or os.getcwd()),
            transcript_path=str(parsed.get("transcriptPath") or parsed.get("transcript_path") or ""),
            session_id=str(parsed.get("sessionId") or parsed.get("session_id") or ""),
            turn_index=turn_index,
            tool_result=_freeze_dict(tool_result_data),
            termination_reason=str(parsed.get("terminationReason") or parsed.get("termination_reason") or ""),
            fully_idle=bool(parsed.get("fullyIdle", parsed.get("fully_idle", True))),
        )
