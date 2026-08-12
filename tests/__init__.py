"""Test package bootstrap for the repository's src layout."""

from __future__ import annotations

import sys
from pathlib import Path


SOURCE_DIR = Path(__file__).resolve().parent.parent / "src"
if str(SOURCE_DIR) not in sys.path:
    sys.path.insert(0, str(SOURCE_DIR))
