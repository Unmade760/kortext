"""
Cross-agent session handoff manager.
Encapsulates file-based baton persistence, reading, listing, and completion
across session and agent boundaries.
"""

from datetime import datetime, timezone
import json
import logging
from pathlib import Path
from typing import List, Optional, Union
import uuid

logger = logging.getLogger(__name__)


class HandoffManager:
    """Manages cross-agent context handoff batons."""

    def __init__(self, handoffs_dir: Union[str, Path]) -> None:
        self.handoffs_dir = Path(handoffs_dir)
        self.handoffs_dir.mkdir(parents=True, exist_ok=True)

    def create_baton(
        self,
        target_agent: Optional[str] = None,
        current_scope: Optional[str] = None,
        open_hypotheses: Optional[list[str]] = None,
        unresolved_questions: Optional[list[str]] = None,
        active_blast_radius: Optional[list[str]] = None,
    ) -> str:
        """Create a new cross-agent handoff baton."""
        now = datetime.now(timezone.utc).isoformat()
        bid = f"baton_{datetime.now().strftime('%Y%m%d_%H%M%S')}_{uuid.uuid4().hex[:6]}"
        data = {
            "baton_id": bid,
            "created_at": now,
            "source_agent": "antigravity",
            "target_agent": target_agent or "any",
            "current_scope": current_scope or "",
            "open_hypotheses": open_hypotheses or [],
            "unresolved_questions": unresolved_questions or [],
            "active_blast_radius": active_blast_radius or [],
            "status": "pending",
        }
        baton_path = self.handoffs_dir / f"{bid}.json"
        with open(baton_path, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2)

        return (
            f"✅ Created cross-agent handoff baton: {bid}\n"
            f"   → Target: {data['target_agent']}\n"
            f"   → Scope: {data['current_scope']}\n"
            f"   → Open hypotheses: {len(data['open_hypotheses'])}\n"
            f"   → Unresolved questions: {len(data['unresolved_questions'])}\n"
            f"   → Active blast radius: {len(data['active_blast_radius'])}\n"
            f"   → Path: {baton_path}"
        )

    def read_baton(
        self,
        baton_id: Optional[str] = None,
        target_agent: Optional[str] = None,
    ) -> str:
        """Read a handoff baton by ID or the latest pending baton for target_agent."""
        files = sorted(self.handoffs_dir.glob("baton_*.json"), reverse=True)
        if not files:
            return "⚠️ No cross-agent handoff batons found in journal/handoffs/."

        target_file = None
        if baton_id:
            for f in files:
                if baton_id in f.name:
                    target_file = f
                    break
        else:
            for f in files:
                try:
                    with open(f, "r", encoding="utf-8") as jf:
                        d = json.load(jf)
                    if d.get("status") == "pending":
                        if not target_agent or d.get("target_agent") in (target_agent, "any"):
                            target_file = f
                            break
                except Exception:
                    continue

        if not target_file:
            return f"⚠️ No matching handoff baton found (baton_id={baton_id}, target_agent={target_agent})."

        with open(target_file, "r", encoding="utf-8") as jf:
            data = json.load(jf)
        return json.dumps(data, indent=2)

    def list_batons(self, limit: int = 10) -> str:
        """List recent pending handoff batons up to limit."""
        files = sorted(self.handoffs_dir.glob("baton_*.json"), reverse=True)
        summaries = []
        for f in files[:limit]:
            try:
                with open(f, "r", encoding="utf-8") as jf:
                    d = json.load(jf)
                summaries.append({
                    "baton_id": d.get("baton_id"),
                    "created_at": d.get("created_at"),
                    "target_agent": d.get("target_agent"),
                    "current_scope": d.get("current_scope"),
                    "status": d.get("status"),
                })
            except Exception:
                pass
        return json.dumps({"pending_batons": summaries}, indent=2)

    def complete_baton(self, baton_id: Optional[str] = None) -> str:
        """Mark a handoff baton as completed."""
        if not baton_id:
            return "⚠️ Please provide baton_id to mark complete."
        matched = list(self.handoffs_dir.glob(f"*{baton_id}*.json"))
        if not matched:
            return f"⚠️ Baton '{baton_id}' not found."
        with open(matched[0], "r", encoding="utf-8") as jf:
            data = json.load(jf)
        now = datetime.now(timezone.utc).isoformat()
        data["status"] = "completed"
        data["completed_at"] = now
        with open(matched[0], "w", encoding="utf-8") as jf:
            json.dump(data, jf, indent=2)
        return f"✅ Handoff baton '{data['baton_id']}' marked as completed."

    def execute(
        self,
        action: str = "create",
        target_agent: Optional[str] = None,
        current_scope: Optional[str] = None,
        open_hypotheses: Optional[list[str]] = None,
        unresolved_questions: Optional[list[str]] = None,
        active_blast_radius: Optional[list[str]] = None,
        baton_id: Optional[str] = None,
    ) -> str:
        """Dispatch handoff action to the appropriate handler method."""
        action_norm = action.lower().strip()
        if action_norm == "create":
            return self.create_baton(
                target_agent=target_agent,
                current_scope=current_scope,
                open_hypotheses=open_hypotheses,
                unresolved_questions=unresolved_questions,
                active_blast_radius=active_blast_radius,
            )
        elif action_norm == "read":
            return self.read_baton(baton_id=baton_id, target_agent=target_agent)
        elif action_norm == "list":
            return self.list_batons()
        elif action_norm == "complete":
            return self.complete_baton(baton_id=baton_id)
        return f"⚠️ Unknown action '{action}'. Use create, read, list, or complete."
