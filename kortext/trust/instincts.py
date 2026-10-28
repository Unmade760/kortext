"""
Instinct-Based Continuous Learning Store (ECC continuous-learning-v2 pattern).

Records project-scoped atomic instincts from tool executions, error-fix pairs,
and verified session outcomes with confidence scoring (0.3 -> 0.95) and provenance
trust-tier tracking ('speculative', 'tool_confirmed', 'verified', 'user_approved').
High-confidence verified instincts (>= 0.8) are eligible for skill distillation
and invariant induction during Dream Mode consolidation.
"""
from __future__ import annotations

from datetime import datetime, timezone
import hashlib
import json
import logging
import os
import uuid
from pathlib import Path
import re
from typing import Any, Dict, List, Optional, Tuple

from kortext._home import get_kortext_home

logger = logging.getLogger(__name__)

EXECUTABLE_TRUST_LEVELS = frozenset({"tool_confirmed", "verified", "user_approved", "system"})

# Process-local (mtime_ns, size) cache keyed by resolved store_path
_INSTINCT_FILE_CACHE: Dict[str, Tuple[int, int, Dict[str, Dict[str, Any]]]] = {}


def _slugify(text: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-")
    return slug[:48] or "learned-instinct"


class InstinctStore:
    """Manages atomic project-scoped instincts, provenance trust tiers, and confidence evolution."""

    def __init__(
        self,
        store_path: Optional[Path] = None,
        storage_path: Optional[Path] = None,
    ):
        resolved = store_path or storage_path or (get_kortext_home() / "instincts.json")
        self.store_path = Path(resolved)
        self.storage_path = self.store_path
        self.store_path.parent.mkdir(parents=True, exist_ok=True)

    def _load(self) -> Dict[str, Dict[str, Any]]:
        if not self.store_path.is_file():
            return {}
        try:
            st = self.store_path.stat()
            cache_key = str(self.store_path.resolve())
            cached = _INSTINCT_FILE_CACHE.get(cache_key)
            if cached is not None and cached[0] == st.st_mtime_ns and cached[1] == st.st_size:
                return {k: dict(v) for k, v in cached[2].items()}

            data = json.loads(self.store_path.read_text(encoding="utf-8"))
            if not isinstance(data, dict):
                return {}
            # Defensive migration for legacy {"instincts": [...]} list format
            if "instincts" in data and isinstance(data["instincts"], list):
                migrated: Dict[str, Dict[str, Any]] = {
                    k: v for k, v in data.items() if k != "instincts" and isinstance(v, dict)
                }
                for item in data["instincts"]:
                    if isinstance(item, dict):
                        iid = str(
                            item.get("id")
                            or (
                                "inst_"
                                + hashlib.sha256(
                                    f"{item.get('project', 'kortext')}:{item.get('domain', 'general')}:{str(item.get('pattern', '')).lower()}".encode("utf-8")
                                ).hexdigest()[:10]
                            )
                        )
                        item_copy = dict(item)
                        item_copy.setdefault("id", iid)
                        migrated[iid] = item_copy
                _INSTINCT_FILE_CACHE[cache_key] = (st.st_mtime_ns, st.st_size, migrated)
                return {k: dict(v) for k, v in migrated.items()}

            cleaned = {k: v for k, v in data.items() if isinstance(v, dict)}
            _INSTINCT_FILE_CACHE[cache_key] = (st.st_mtime_ns, st.st_size, cleaned)
            return {k: dict(v) for k, v in cleaned.items()}
        except Exception as e:
            logger.debug("Failed loading instincts store: %s", e)
            return {}

    def _save(self, data: Dict[str, Dict[str, Any]]) -> None:
        try:
            self.store_path.parent.mkdir(parents=True, exist_ok=True)
            tmp_path = self.store_path.with_suffix(f".tmp.{os.getpid()}.{uuid.uuid4().hex}")
            tmp_path.write_text(json.dumps(data, indent=2), encoding="utf-8")
            tmp_path.replace(self.store_path)
            st = self.store_path.stat()
            cache_key = str(self.store_path.resolve())
            _INSTINCT_FILE_CACHE[cache_key] = (st.st_mtime_ns, st.st_size, {k: dict(v) for k, v in data.items() if isinstance(v, dict)})
        except Exception as e:
            logger.debug("Failed saving instincts store: %s", e)

    def observe(
        self,
        pattern: str,
        action: str,
        domain: str = "general",
        project: str = "kortext",
        confidence_delta: float = 0.2,
        initial_confidence: float = 0.35,
        confidence: Optional[float] = None,
        trust_level: str = "tool_confirmed",
    ) -> Dict[str, Any]:
        """Records an observation of an atomic instinct and increments its confidence score."""
        if confidence is not None:
            initial_confidence = float(confidence)
        clean_pattern = pattern.strip()
        clean_action = action.strip()
        norm_trust = (trust_level or "tool_confirmed").strip().lower()
        data = self._load()
        matched_id = None
        for eid, erec in data.items():
            if (
                isinstance(erec, dict)
                and str(erec.get("domain", "")).lower() == domain.lower()
                and str(erec.get("pattern", "")).lower() == clean_pattern.lower()
            ):
                matched_id = eid
                break
        key_raw = f"{project}:{domain}:{clean_pattern.lower()}"
        inst_id = matched_id or ("inst_" + hashlib.sha256(key_raw.encode("utf-8")).hexdigest()[:10])
        now = datetime.now(timezone.utc).isoformat()

        if inst_id in data:
            rec = data[inst_id]
            obs_count = int(rec.get("observations", rec.get("evidence_count", 1))) + 1
            rec["observations"] = obs_count
            rec["evidence_count"] = obs_count
            rec["confidence"] = round(min(0.95, float(rec.get("confidence", initial_confidence)) + confidence_delta), 2)
            rec["updated_at"] = now
            if clean_action:
                rec["action"] = clean_action
            projects = list(rec.get("projects") or rec.get("projects_seen") or [rec.get("project", project)])
            if project and project not in projects:
                projects.append(project)
            rec["projects"] = projects
            rec["projects_seen"] = list(projects)
            if len(projects) >= 2:
                rec["scope"] = "global"
            if norm_trust in EXECUTABLE_TRUST_LEVELS or not rec.get("trust_level"):
                rec["trust_level"] = norm_trust
        else:
            rec = {
                "id": inst_id,
                "skill_name": f"instinct-{_slugify(domain)}-{inst_id[-4:]}",
                "pattern": clean_pattern,
                "action": clean_action,
                "domain": domain,
                "project": project,
                "projects": [project],
                "projects_seen": [project],
                "scope": "project",
                "trust_level": norm_trust,
                "confidence": round(initial_confidence, 2),
                "observations": 1,
                "evidence_count": 1,
                "distilled": False,
                "created_at": now,
                "updated_at": now,
            }
            data[inst_id] = rec

        self._save(data)
        if project and project.lower() != "all":
            try:
                proj_slug = re.sub(r"[^a-zA-Z0-9_\-]+", "_", project.strip()) or "kortext"
                proj_file = self.store_path.parent / "projects" / proj_slug / "instincts.json"
                proj_file.parent.mkdir(parents=True, exist_ok=True)
                proj_data = {
                    k: v
                    for k, v in data.items()
                    if isinstance(v, dict)
                    and (
                        str(v.get("project", "")).lower() == project.lower()
                        or project in (v.get("projects") or [])
                        or v.get("scope") == "global"
                    )
                }
                tmp_pf = proj_file.with_suffix(f".tmp.{os.getpid()}")
                tmp_pf.write_text(json.dumps(proj_data, indent=2), encoding="utf-8")
                tmp_pf.replace(proj_file)
            except OSError as exc:
                logger.debug("Project-scoped instinct mirror skipped: %s", exc)
        return rec

    record_instinct = observe

    def load_all(self, project: Optional[str] = None) -> List[Dict[str, Any]]:
        """Returns all stored instincts (optionally filtered by project), sorted by confidence desc."""
        data = self._load()
        items: List[Dict[str, Any]] = []
        for rec in data.values():
            if not isinstance(rec, dict):
                continue
            rec_copy = dict(rec)
            obs = int(rec_copy.get("observations", rec_copy.get("evidence_count", 1)) or 1)
            rec_copy["observations"] = obs
            rec_copy["evidence_count"] = obs
            rec_copy.setdefault("trust_level", "tool_confirmed")
            if project and project.lower() != "all":
                rec_proj = str(rec_copy.get("project") or "kortext")
                if rec_proj.lower() != project.lower() and rec_copy.get("scope") != "global":
                    continue
            items.append(rec_copy)
        items.sort(key=lambda r: (float(r.get("confidence", 0.0)), int(r.get("observations", 0))), reverse=True)
        return items

    def get_active_instincts(
        self,
        min_confidence: float = 0.0,
        project: Optional[str] = None,
    ) -> List[Dict[str, Any]]:
        """Returns active instincts meeting min_confidence."""
        return [
            r for r in self.load_all(project=project)
            if float(r.get("confidence", 0.0)) >= min_confidence
        ]

    def get_high_confidence_instincts(
        self,
        min_confidence: float = 0.8,
        project: Optional[str] = None,
        only_undistilled: bool = True,
        require_verified_trust: bool = False,
    ) -> List[Dict[str, Any]]:
        """Returns instincts whose confidence >= min_confidence for skill distillation."""
        results: List[Dict[str, Any]] = []
        for rec in self.load_all(project=project):
            if float(rec.get("confidence", 0.0)) < min_confidence:
                continue
            if only_undistilled and rec.get("distilled", False):
                continue
            if require_verified_trust and str(rec.get("trust_level", "tool_confirmed")).lower() not in EXECUTABLE_TRUST_LEVELS:
                continue
            results.append(rec)
        return results

    def approve_instinct(self, inst_id: str) -> Optional[Dict[str, Any]]:
        """Promotes an instinct to user_approved trust level and >=0.85 confidence."""
        data = self._load()
        if inst_id not in data:
            return None
        rec = data[inst_id]
        rec["trust_level"] = "user_approved"
        rec["confidence"] = max(0.85, float(rec.get("confidence", 0.85)))
        rec["updated_at"] = datetime.now(timezone.utc).isoformat()
        self._save(data)
        return dict(rec)

    def mark_distilled(self, inst_id: str, skill_path: str) -> None:
        data = self._load()
        if inst_id in data:
            data[inst_id]["distilled"] = True
            data[inst_id]["skill_path"] = skill_path
            data[inst_id]["distilled_skill_path"] = skill_path
            data[inst_id]["distilled_at"] = datetime.now(timezone.utc).isoformat()
            self._save(data)
