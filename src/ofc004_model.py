"""Canonical OFC-004 process model loaded from its reviewed IR artifact."""

from __future__ import annotations

from ir import load_ir
from project_paths import EXAMPLE_IR_DIR


MODEL = load_ir(EXAMPLE_IR_DIR / "OFC-004.ir.json")
NODES = MODEL.nodes
EDGES = MODEL.edges
LANES = MODEL.lanes
PHASES = MODEL.phases
ANN_ABOVE = MODEL.ann_above
BY_ID = MODEL.by_id()
