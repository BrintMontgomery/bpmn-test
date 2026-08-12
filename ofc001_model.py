"""OFC-001 process model and preview-only presentation metadata.

The workflow itself is the canonical ``OFC-001.ir.json`` artifact.  This
module keeps the richer preview copy used by ``build_preview.py`` alongside
the loaded IR model.
"""

from __future__ import annotations

from pathlib import Path

from bpmn_engine import PreviewMetadata, ProcessOption
from ir import load_ir


MODEL = load_ir(Path(__file__).with_name("OFC-001.ir.json"))

PROCESS_OPTIONS = [
    ProcessOption(
        "A",
        "Arrival Without Advance Notice",
        "The Deputy arrives without calling ahead or outside the scheduled time.",
        "Gateway_UnscheduledArrival",
        "Verify the consumer against the admission email and daily plan, "
        "update the packet, then rejoin at the sally-port admission.",
    ),
    ProcessOption(
        "B",
        "Changed or Rescheduled Admission",
        "The admission date, arrival time, consumer information, or destination "
        "unit changes before arrival.",
        "Gateway_InfoChanged",
        "Work from the most recent email rather than a packet printed from an "
        "earlier schedule, then rejoin before equipment staging.",
    ),
    ProcessOption(
        "C",
        "Behavioral or Safety Concern",
        "The Deputy reports combative behavior, transport problems, or threats, "
        "or the consumer presents as agitated.",
        "Gateway_SafetyConcern",
        "Record the report, call the unit early, and hold for a nursing "
        "assessment; a second gateway decides whether precautions change "
        "before the Unit Nurse authorizes continuation.",
    ),
    ProcessOption(
        "D",
        "Multiple Admissions or Escort Constraints",
        "Security is processing multiple admissions, or the primary Officer "
        "cannot complete the shower or unit escort.",
        "Gateway_EscortConstraints",
        "Coordinate an alternate escort plan with the Unit Nurse and Mental "
        "Health Technician instead of the standard pairing.",
    ),
    ProcessOption(
        "E",
        "Alternate Shower or Nursing Location",
        "The destination unit directs that the shower or nursing activities "
        "happen in a secure unit location.",
        "Gateway_AltLocation",
        "Escort to the designated location and complete nursing activities "
        "there, bypassing the admissions-area shower entirely.",
    ),
]

MODEL.options = PROCESS_OPTIONS
MODEL.preview = PreviewMetadata(
    title="OFC-001 Security Intake",
    heading="Security Intakes Consumer",
    eyebrow="Operating Checklist · OFC-001",
    lede="The controlled process for receiving a consumer from law enforcement "
         "at the Oklahoma Forensic Center — transfer of custody, security "
         "search, electronic tracking and identification, and the handoff "
         "to nursing staff.",
    owner="OFC Security Unit",
    version="1.1",
    issued="2026-08-11",
    structure_title="Eleven phases, five lanes",
    structure_intro="The process runs left to right in a single pool. "
                     "Admissions Coordinator sits outside it as a collapsed "
                     "participant, sending the scheduled admission email that "
                     "starts the process. Dots mark which actors appear in "
                     "each phase.",
    variation_title="The five options are gateways, not footnotes",
    variation_intro="Options A–E in the checklist describe departures from "
                    "the main path. Each one is modeled where it actually "
                    "occurs, as a labeled exclusive gateway with a condition "
                    "on the non-default branch.",
    constraints_title="Notes carried onto the diagram",
    constraints_intro="Each note from the checklist is attached to the task "
                      "it governs as a BPMN text annotation, so the "
                      "constraint travels with the model rather than living "
                      "in a separate document.",
    footer="Oklahoma Forensic Center · Security Unit · OFC-001 v1.1 · "
           "generated from OFC-001.ir.json",
)

NODES = MODEL.nodes
EDGES = MODEL.edges
LANES = MODEL.lanes
PHASES = MODEL.phases
ANN_ABOVE = MODEL.ann_above
BY_ID = MODEL.by_id()
SO, LED, CON, UN, MHT = (lane_id for lane_id, _ in LANES)
