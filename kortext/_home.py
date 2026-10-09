"""
Kortext storage home resolution utility.
Resolves ~/.kortext or legacy ~/.cerebrum data directory.
"""

import os
from pathlib import Path


def get_kortext_home() -> Path:
    env_home = os.getenv("KORTEXT_HOME") or os.getenv("CEREBRUM_HOME")
    if env_home:
        return Path(env_home)
    k_dir = Path.home() / ".kortext"
    if k_dir.exists():
        return k_dir
    c_dir = Path.home() / ".cerebrum"
    if c_dir.exists():
        return c_dir
    return k_dir


KORTEXT_HOME = get_kortext_home()
CEREBRUM_HOME = KORTEXT_HOME
