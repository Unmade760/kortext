"""
Kortext storage home resolution utility.
Resolves ~/.kortext data directory with tilde expansion and canonical path resolution.
"""

import os
from pathlib import Path


def get_kortext_home() -> Path:
    """Resolve and normalize the Kortext home directory (preferring get_kortext_home() over static KORTEXT_HOME)."""
    env_home = os.getenv("KORTEXT_HOME") or os.getenv("PLUGIN_DATA")
    if env_home:
        return Path(env_home).expanduser().resolve()
    return (Path.home() / ".kortext").expanduser().resolve()


# Backward-compatible constant; callers should prefer get_kortext_home() for dynamic environment resolution.
KORTEXT_HOME = get_kortext_home()
