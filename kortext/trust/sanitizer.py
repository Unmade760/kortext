"""
Kortext MINJA Adversarial Causal Sanitizer.
Protects persistent memory from indirect prompt injections and unauthorized directive assertion.
"""

from __future__ import annotations

import json
import logging
import os
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from kortext._home import KORTEXT_HOME

logger = logging.getLogger("kortext.security")

INJECTION_PATTERNS = [
    r"(?i)ignore\s+(all\s+)?(previous|prior)\s+(instructions|directives|prompts)",
    r"(?i)you\s+are\s+now\s+(an?\s+)?(unrestricted|evil|dan|new)",
    r"(?i)system\s+override",
    r"(?i)\[\s*system\s*\]",
    r"(?i)<\s*system\s*>",
    r"(?i)always\s+(output|reveal|dump|leak)\s+(api_key|password|credential|\.env)",
    r"(?i)curl\s+.*(-(-data\w*|data|form|upload-file)|-(d|F|X\s*POST|T))\s*.*https?://",
    r"(?i)curl\s+.*https?://[^\s]+\s*.*(-(-data\w*|data|form|upload-file)|-(d|F|X\s*POST|T))",
    r"(?i)curl\s+.*https?://.*((\b|_)(secret|token|key|cred|password|api_key|auth|payload|attacker|evil|hacker|exfiltrat)|\.env|\|\s*(ba)?sh)",
    r"(?i)send\s+(secrets|tokens?|keys?)\s+to",
]

COMPILED_PATTERNS = [re.compile(p) for p in INJECTION_PATTERNS]


class SecurityViolation(Exception):
    """Raised when an adversarial injection attempt is detected."""


class CausalSanitizer:
    """Guards memory write operations against adversarial poisoning."""

    def __init__(self, quarantine_dir: Optional[Path] = None):
        self.quarantine_dir = quarantine_dir or (KORTEXT_HOME / "quarantine")
        self.quarantine_dir.mkdir(parents=True, exist_ok=True)

    def sanitize(
        self,
        subject: str,
        relation: str,
        fact: str,
        source_tier: int = 2,
    ) -> bool:
        """
        Validates proposed memory write.
        Raises SecurityViolation if malicious patterns or unauthorized privilege escalation is detected.
        """
        # 1. Tier 3 (External untrusted input) privilege gate
        if source_tier >= 3:
            normative_words = ["always", "never", "must", "invariant", "directive", "protocol"]
            if any(w in fact.lower() for w in normative_words):
                self._quarantine_violation(subject, relation, fact, "Tier 3 privilege escalation attempt")
                raise SecurityViolation("Tier 3 external inputs cannot assert normative rules or invariants.")

        # 2. Regex Pattern Matching
        for pattern in COMPILED_PATTERNS:
            if pattern.search(fact) or pattern.search(subject):
                self._quarantine_violation(subject, relation, fact, f"Matched pattern: {pattern.pattern}")
                raise SecurityViolation(f"Adversarial injection marker detected: {pattern.pattern}")

        return True

    def _quarantine_violation(self, subject: str, relation: str, fact: str, reason: str):
        """Persists rejected injection attempts to quarantine for security forensics."""
        ts = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S_%f")
        payload = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "reason": reason,
            "subject": subject,
            "relation": relation,
            "fact": fact,
        }
        out_file = self.quarantine_dir / f"blocked_injection_{ts}.json"
        out_file.write_text(json.dumps(payload, indent=2), encoding="utf-8")
        logger.critical(f"ADVERSARIAL INJECTION BLOCKED AND QUARANTINED: {out_file}")
