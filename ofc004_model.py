"""Canonical OFC-004 process model loaded from its reviewed IR artifact."""

from __future__ import annotations

from pathlib import Path

from ir import load_ir


MODEL = load_ir(Path(__file__).with_name("OFC-004.ir.json"))
NODES = MODEL.nodes
EDGES = MODEL.edges
LANES = MODEL.lanes
PHASES = MODEL.phases
ANN_ABOVE = MODEL.ann_above
BY_ID = MODEL.by_id()

