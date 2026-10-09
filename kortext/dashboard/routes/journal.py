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


VALID_CATEGORIES = frozenset({
    "decision", "roadmap", "implementation", "experiment",
    "benchmark", "investigation", "research", "report", "dream",
})

CATEGORY_FOLDER_MAP = {
    "decisions": "decision",
    "roadmaps": "roadmap",
    "implementations": "implementation",
    "experiments": "experiment",
    "benchmarks": "benchmark",
    "investigations": "investigation",
    "research": "research",
    "reports": "report",
    "dreams": "report",
}


def _extract_category(body: str, folder_hint: Optional[str] = None) -> str:
    """Extracts or infers category from markdown metadata, tags, or folder location."""
    cat_match = (
        re.search(r"[-*]\s*\*\*Category:\*\*\s*([a-zA-Z0-9_\-]+)", body, re.IGNORECASE)
        or re.search(r"\*\*Category:\*\*\s*([a-zA-Z0-9_\-]+)", body, re.IGNORECASE)
        or re.search(r"\[Category:\s*([^\]]+)\]", body, re.IGNORECASE)
    )
    if cat_match:
        val = cat_match.group(1).strip().lower()
        if val in VALID_CATEGORIES:
            return val
        if val in CATEGORY_FOLDER_MAP:
            return CATEGORY_FOLDER_MAP[val]

    if folder_hint and folder_hint.lower() in CATEGORY_FOLDER_MAP:
        return CATEGORY_FOLDER_MAP[folder_hint.lower()]

    # Infer from keywords
    body_lower = body.lower()
    if "decision:" in body_lower or "adr:" in body_lower or "architectural decision" in body_lower:
        return "decision"
    if "roadmap:" in body_lower or "milestone:" in body_lower:
        return "roadmap"
    if "benchmark:" in body_lower or "benchmarking" in body_lower:
        return "benchmark"
    if "experiment:" in body_lower:
        return "experiment"
    if "investigation:" in body_lower or "root cause" in body_lower:
        return "investigation"
    if "dream cycle" in body_lower or "dream report" in body_lower:
        return "report"

    return "implementation"


@router.get("/api/journal")
async def get_journal():
    """Parses all journal files and returns chronological entries with categories."""
    if not JOURNAL_DIR.is_dir():
        return {"entries": []}

    entries = []
    seen_keys = set()

    # 1. Parse daily markdown journals (e.g. journal/2026-10-10.md)
    daily_files = sorted(JOURNAL_DIR.glob("*.md"), reverse=True)
    for f in daily_files:
        if f.name.startswith(".") or f.stem in ("README", "invariants"):
            continue
        date_str = f.stem
        try:
            content = f.read_text(encoding="utf-8")
            sections = re.split(r"(?m)^##\s+", content)
            for sec in sections[1:]:
                lines = sec.strip().split("\n")
                if not lines:
                    continue
                header = lines[0].strip()
                body = "\n".join(lines[1:]).strip()

                tags = []
                project = None
                tag_match = re.search(r"\*\*Tags:\*\*\s*(.*)", body)
                if tag_match:
                    tags = [t.strip() for t in tag_match.group(1).split(",") if t.strip()]
                proj_match = re.search(r"\[Project:\s*([^\]]+)\]", body) or re.search(r"\*\*Project:\*\*\s*(.*)", body)
                if proj_match:
                    project = proj_match.group(1).strip()

                category = _extract_category(body)

                dedup_key = f"{date_str}:{header.lower()}"
                if dedup_key in seen_keys:
                    continue
                seen_keys.add(dedup_key)

                entries.append({
                    "date": date_str,
                    "title": header,
                    "body": body,
                    "category": category,
                    "tags": tags,
                    "project": project,
                })
        except Exception:
            continue

    # 2. Parse dedicated category directories (e.g. journal/decisions/*.md, journal/reports/*.md)
    for folder_name, cat_name in CATEGORY_FOLDER_MAP.items():
        sub_dir = JOURNAL_DIR / folder_name
        if not sub_dir.is_dir():
            continue
        sub_files = sorted(sub_dir.glob("*.md"), reverse=True)
        for sf in sub_files:
            if sf.name.startswith("."):
                continue
            try:
                content = sf.read_text(encoding="utf-8")
                # Check if it has a top-level # Title
                title = sf.stem.replace("_", " ").replace("-", " ").title()
                date_str = sf.stem[:10] if len(sf.stem) >= 10 and sf.stem[:4].isdigit() else "2026-10-10"
                body = content

                h1_match = re.search(r"^#\s+(.*)", content)
                if h1_match:
                    title = h1_match.group(1).strip()

                date_match = re.search(r"[-*]\s*\*\*Date:\*\*\s*([0-9]{4}-[0-9]{2}-[0-9]{2})", content)
                if date_match:
                    date_str = date_match.group(1)

                tags = []
                tag_match = re.search(r"[-*]\s*\*\*Tags:\*\*\s*(.*)", content)
                if tag_match:
                    tags = [t.strip() for t in tag_match.group(1).split(",") if t.strip()]

                project = None
                proj_match = re.search(r"[-*]\s*\*\*Project:\*\*\s*(.*)", content) or re.search(r"\[Project:\s*([^\]]+)\]", content)
                if proj_match:
                    project = proj_match.group(1).strip()

                category = _extract_category(content, folder_hint=folder_name)

                dedup_key = f"{date_str}:{title.lower()}"
                if dedup_key in seen_keys:
                    continue
                seen_keys.add(dedup_key)

                entries.append({
                    "date": date_str,
                    "title": title,
                    "body": body,
                    "category": category,
                    "tags": tags,
                    "project": project,
                })
            except Exception:
                continue

    # Sort descending by date
    entries.sort(key=lambda e: str(e.get("date", "")), reverse=True)
    return {"entries": entries}
