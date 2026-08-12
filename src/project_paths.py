"""Stable locations for repository-managed sample files and browser assets."""

from __future__ import annotations

from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parent.parent
ASSETS_DIR = PROJECT_ROOT / "assets"
EXAMPLES_DIR = PROJECT_ROOT / "examples"
EXAMPLE_MARKDOWN_DIR = EXAMPLES_DIR / "markdown"
EXAMPLE_IR_DIR = EXAMPLES_DIR / "ir"
EXAMPLE_BPMN_DIR = EXAMPLES_DIR / "bpmn"
