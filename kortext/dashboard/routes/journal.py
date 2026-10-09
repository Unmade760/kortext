"""
Journal parsing and file reading route handlers.
"""

import os
import re
from pathlib import Path
from typing import Any, Dict, List, Optional

from fastapi import APIRouter

router = APIRouter(tags=["journal"])

KORTEXT_ROOT = Path(__file__).resolve().parents[3]
CEREBRUM_ROOT = KORTEXT_ROOT
JOURNAL_DIR = Path(os.getenv("JOURNAL_DIR", str(KORTEXT_ROOT / "journal")))


@router.get("/api/journal")
async def get_journal():
    """Parses all journal files and returns chronological entries."""
    if not JOURNAL_DIR.is_dir():
        return {"entries": []}

    entries = []
    files = sorted(JOURNAL_DIR.glob("*.md"), reverse=True)
    for f in files:
        date_str = f.stem
        try:
            content = f.read_text(encoding="utf-8")
            # Split sections by ##
            sections = re.split(r"(?m)^##\s+", content)
            for sec in sections[1:]:
                lines = sec.strip().split("\n")
                if not lines:
                    continue
                header = lines[0].strip()
                body = "\n".join(lines[1:]).strip()

                # Extract tags and project if present
                tags = []
                project = None
                tag_match = re.search(r"\*\*Tags:\*\*\s*(.*)", body)
                if tag_match:
                    tags = [t.strip() for t in tag_match.group(1).split(",")]
                proj_match = re.search(r"\[Project:\s*([^\]]+)\]", body) or re.search(r"\*\*Project:\*\*\s*(.*)", body)
                if proj_match:
                    project = proj_match.group(1).strip()

                entries.append({
                    "date": date_str,
                    "title": header,
                    "body": body,
                    "tags": tags,
                    "project": project,
                })
        except Exception:
            continue

    return {"entries": entries}
