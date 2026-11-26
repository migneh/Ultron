"""Stable deployment paths, distinct from packaged source/resources.

Default keeps existing checkout config/memory/logs locations. Installed deployments
can set ULTRON_HOME to an existing deployment directory; frozen builds use the
executable directory. No directory creation or credential migration at import.
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

PACKAGE_ROOT = Path(__file__).resolve().parent
PROJECT_ROOT = Path(os.environ.get("ULTRON_HOME") or (
    str(Path(sys.executable).resolve().parent) if getattr(sys, "frozen", False)
    else str(PACKAGE_ROOT.parent if (PACKAGE_ROOT.parent / "pyproject.toml").is_file() else Path.home() / ".ultron"))).expanduser().resolve()
CONFIG_DIR = PROJECT_ROOT / "config"
STATE_DIR = PROJECT_ROOT / "memory"
LOGS_DIR = PROJECT_ROOT / "logs"

ASSETS_DIR = PACKAGE_ROOT / "assets"
