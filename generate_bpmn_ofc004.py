"""Generate the OFC-004 Case Manager Intakes Consumer BPMN 2.0 diagram.

The process is described once, declaratively, in NODES / EDGES below. This
script computes the diagram layout and emits OFC-004.bpmn — a BPMN 2.0 XML
with full DI, opens in Camunda Modeler, bpmn.io, Signavio, etc.

Source: "OFC-004 — Case Manager Intakes Consumer.md", Main Path and Options.

To change the diagram, edit the model below and re-run this script. Do not
hand-edit OFC-004.bpmn -- it is overwritten.
"""

from __future__ import annotations

import xml.dom.minidom as minidom
import xml.etree.ElementTree as ET
from dataclasses import dataclass, field
from pathlib import Path

# --------------------------------------------------------------------------
# Geometry constants
# --------------------------------------------------------------------------

TASK_W, TASK_H = 140, 80
GW_W, GW_H = 50, 50
EV_W, EV_H = 36, 36
ANN_W = 280
ANN_LINE = 15
ANN_CHARS = 44

COL_GAP = 78
ROW_PITCH = 150
GW_LBL_W = 140
LANE_PAD = 15
POOL_HEADER = 30
POOL_X = 200
POOL_Y = 260

LANES = [
    ("Lane_CM", "Case Manager"),
    ("Lane_CON", "Consumer"),
    ("Lane_SW", "Social Worker"),
    ("Lane_NS", "Nursing Staff"),
    ("Lane_FS", "Floor Staff"),
    ("Lane_PTA", "Prospective Treatment Advocate"),
    ("Lane_PC", "Prospective Contact"),
]

CM, CON, SW, NS, FS, PTA, PC = (lane_id for lane_id, _ in LANES)

ANN_ABOVE = {CM}

PHASES = [
    ("P0", "Trigger"),
    ("P1", "1. Elopement Form & Protective Order Review"),
    ("P2", "2. Complete & Distribute Elopement Form"),
    ("P3", "3. Treatment Advocate Designation"),
    ("P4", "4. Nursing Handoff"),
    ("P5", "5. Contact Sheet Review"),
    ("P6", "6. ROI Filing & Closeout"),
]


# --------------------------------------------------------------------------
# Model
# --------------------------------------------------------------------------


@dataclass
class Node:
    id: str
    kind: str
    lane: str
    col: int
    name: str
    phase: str
    subrow: int = 0
    ttype: str = "manual"
    doc: list[str] = field(default_factory=list)
    note: str | None = None


@dataclass
class Edge:
    source: str
    target: str
    label: str = ""
    condition: str = ""
    loop: bool = False


N = Node
E = Edge

NODES: list[Node] = [
    # -- Trigger ----------------------------------------------------------
    N("StartEvent_AdmissionNotification", "start_message", CM, 0,
      "Admission notification email and consumer report received", "P0",
      doc=["Receive the admission notification email and associated "
           "consumer report."]),

    # -- P1: Elopement Form & Protective Order Review -------------------
    N("Task_BeginElopementForm", "task", CM, 1,
      "Begin the Elopement Form", "P1", ttype="user",
      doc=["Open and begin the Elopement Form with available information."]),
    N("Task_ReviewAdmissionReport", "task", CM, 2,
      "Review the admission report for contacts, attorneys, sheriff "
      "information, and victims", "P1", ttype="user",
      doc=["Search the admission report for emergency contacts, county "
           "contacts, attorneys, sheriff information, and victim information."]),
    N("Task_SearchOSCN", "task", CM, 3,
      "Search OSCN for protective orders", "P1", ttype="user",
      doc=["Search the Oklahoma State Courts Network (OSCN) for active "
           "protective orders.",
           "Record applicable contact restrictions on the Elopement Form."]),
    N("Gateway_ProtectiveOrder", "gateway_x", CM, 4,
      "Protective order restricts contact?", "P1",
      doc=["Option B — a protective order involves a proposed or existing "
           "contact."]),
    N("Task_RecordRestrictedPerson", "task", CM, 5,
      "Record the restricted person on the Elopement Form", "P1",
      subrow=1, ttype="user",
      note="[a] Protective orders identified through OSCN restrict contact "
           "with the persons named in the order. A restricted person must not "
           "be approved for consumer contact."),
    N("Task_DoNotAuthorizeContact", "task", CM, 6,
      "Do not authorize contact with the restricted person", "P1",
      subrow=1, ttype="manual"),
    N("Gateway_ConsumerRequestsRestricted", "gateway_x", CM, 7,
      "Consumer requests prohibited contact?", "P1", subrow=1),
    N("Task_InformConsumerOfRestriction", "task", CM, 8,
      "Inform the Consumer of the restriction", "P1", subrow=2,
      ttype="manual"),
    N("Gateway_ProtectiveOrderJoin", "gateway_x", CM, 9,
      "", "P1", subrow=1),

    # -- P2: Complete & Distribute Elopement Form ----------------------
    N("Task_ObtainRemainingInfo", "task", CM, 10,
      "Obtain remaining consumer information after arrival and complete "
      "the Elopement Form", "P2", ttype="user"),
    N("Task_EmailElopementForm", "task", CM, 11,
      "Email the completed Elopement Form to admissions staff", "P2",
      ttype="send"),

    # -- P3: Treatment Advocate Designation (Option C, D) ---------------
    N("Task_ReviewTAFormWithConsumer", "task", CM, 12,
      "Review the Treatment Advocate Form with the Consumer", "P3",
      ttype="user"),
    N("Gateway_ConsumerAbleToParticipate", "gateway_x", CM, 13,
      "Consumer able to participate?", "P3",
      doc=["Option C — the Consumer is too agitated, delusional, or unable "
           "to participate effectively."]),
    N("Task_PostponeActivity", "task", CM, 14,
      "Postpone the activity", "P3", subrow=1, ttype="manual",
      note="[c] Postpone the affected interview or documentation activity. "
           "Return when the Consumer is able to participate, including the "
           "following day when appropriate. Continue periodic follow-up during "
           "the week when needed."),
    N("Task_ReturnWhenAble", "task", CM, 15,
      "Return when the Consumer is able to participate", "P3", subrow=1,
      ttype="manual"),
    N("Task_PeriodicFollowUp", "task", CM, 16,
      "Continue periodic follow-up during the week", "P3", subrow=1,
      ttype="manual"),
    N("Task_ConsumerIdentifiesAdvocate", "task", CON, 17,
      "Identify a prospective external Treatment Advocate", "P3",
      ttype="manual"),
    N("Task_ContactAdvocate", "task", CM, 18,
      "Contact the Prospective Treatment Advocate", "P3", ttype="send",
      doc=["Obtain confirmation that the person is willing to serve in that "
           "role."]),
    N("Task_AdvocateSignsForm", "task", PTA, 20,
      "Sign the Treatment Advocate Form", "P3", ttype="manual"),
    N("Task_ConsumerSignsROI", "task", CON, 21,
      "Sign the associated Release of Information authorization", "P3",
      subrow=1, ttype="manual"),
    N("Task_ScanDocumentation", "task", CM, 22,
      "Scan a copy of the completed treatment-advocate documentation",
      "P3", ttype="user",
      note="[b] Release of information is limited to the information or "
           "purposes authorized on the signed ROI. Authorization is not a "
           "general release of all consumer information."),
    N("Task_MailCopyToAdvocate", "task", CM, 23,
      "Mail a copy to the Treatment Advocate", "P3", ttype="send"),
    N("Gateway_AdvocateChangeRequested", "gateway_x", CM, 24,
      "Consumer requests a different Treatment Advocate?", "P3",
      doc=["Option D — the Consumer requests a different Treatment Advocate "
           "after the initial designation."]),
    N("Task_ProcessAdvocateChange", "task", CM, 25,
      "Process the new Treatment Advocate designation", "P3", subrow=1,
      ttype="user",
      note="[d] A Consumer may change the designated Treatment Advocate at "
           "any time and may request additions or removals from the contact "
           "sheet after admission."),
    N("Gateway_AdvocateChangeJoin", "gateway_x", CM, 26,
      "", "P3", subrow=1),

    # -- P4: Nursing Handoff -----------------------------------------------
    N("Task_NursingCompletesAdmission", "task", NS, 27,
      "Nursing Staff completes the nursing portion of the admission", "P4",
      ttype="manual"),

    # -- P5: Contact Sheet Review (Option A) ----------------------------
    N("Task_CheckAdditionalContacts", "task", CM, 28,
      "Check with the Social Worker and Consumer for additional persons",
      "P5", ttype="user"),
    N("Gateway_AdditionalContactRequested", "gateway_x", CM, 29,
      "Consumer requests an additional contact?", "P5",
      doc=["Option A — the Consumer requests that another person be added to "
           "the unit contact sheet."]),
    N("Task_CompleteROI", "task", CM, 30,
      "Complete an ROI with the Consumer", "P5", subrow=1, ttype="user"),
    N("Task_RecordROIPurpose", "task", CM, 31,
      "Record authorized purposes or information categories on the ROI", "P5",
      subrow=1, ttype="user",
      doc=["Include applicable contact purposes such as visit, telephone "
           "call, or televisit."]),
    N("Task_ContactProspectiveContact", "task", CM, 32,
      "Contact the Prospective Contact", "P5", subrow=1, ttype="send",
      doc=["Ask whether the person agrees to receive contact from the "
           "Consumer."]),
    N("Task_ProspectiveContactResponds", "task", PC, 33,
      "Respond with agreement or decline", "P5", subrow=1, ttype="manual"),
    N("Gateway_ContactAgrees", "gateway_x", CM, 34,
      "Prospective Contact agrees?", "P5", subrow=1),
    N("Task_InformFloorStaffNewContact", "task", CM, 35,
      "Inform Floor Staff that the contact may be added to the unit "
      "contact sheet", "P5", subrow=2, ttype="send"),
    N("Task_PlaceROIInChartOptionA", "task", CM, 36,
      "Place the approved ROI in the consumer chart", "P5", subrow=2,
      ttype="manual"),
    N("Task_InformConsumerDeclined", "task", CM, 37,
      "Inform the Consumer and do not authorize the contact", "P5",
      subrow=3, ttype="manual"),
    N("Gateway_ContactJoin", "gateway_x", CM, 39,
      "", "P5", subrow=1),
    N("Task_ConfirmContactSheet", "task", CM, 40,
      "Confirm that the unit contact sheet reflects approved contacts",
      "P5", ttype="user",
      note="[c] The contact sheet is individualized to the unit and is not a "
           "standardized standalone case-management form. Floor Staff maintains "
           "the operational contact information."),
    N("Task_CommunicateVerifiedContacts", "task", CM, 41,
      "Communicate verified contact information to Floor Staff", "P5",
      ttype="send"),
    N("Task_FloorStaffMaintainsSheet", "task", FS, 41,
      "Maintain the operational unit contact sheet", "P5", ttype="manual"),

    # -- P6: ROI Filing & Closeout (Option E, F) ------------------------
    N("Task_FileApprovedROIs", "task", CM, 42,
      "Ensure each approved ROI is placed in the consumer chart", "P6",
      ttype="user"),
    N("Gateway_ClinicalEventWitnessed", "gateway_x", CM, 43,
      "Event requiring clinical documentation witnessed?", "P6",
      doc=["Option F — the Case Manager personally witnesses an event that "
           "requires documentation."]),
    N("Task_DocumentInAvatar", "task", CM, 44,
      "Document the event in Avatar", "P6", subrow=1, ttype="user",
      note="[e] Avatar is not part of the routine case-management "
           "admission-document workflow. The Case Manager uses Avatar when an "
           "observed event independently requires documentation. Do not enter "
           "routine Elopement Forms, Treatment Advocate Forms, or admission "
           "ROIs into Avatar solely as part of this intake workflow."),
    N("Gateway_ClinicalEventJoin", "gateway_x", CM, 45,
      "", "P6", subrow=1),
    N("Gateway_PostAdmissionChange", "gateway_x", CM, 46,
      "Contact-list change requested after admission?", "P6",
      doc=["Option E — the Consumer requests that a person be added to or "
           "removed from the contact sheet after the initial admission process."]),
    N("Task_ProcessContactChange", "task", CM, 47,
      "Process the requested change", "P6", subrow=1, ttype="user"),
    N("Task_VerifyROIForChange", "task", CM, 48,
      "Complete and verify an ROI when required", "P6", subrow=1,
      ttype="user"),
    N("Task_CommunicateChangeToFloorStaff", "task", CM, 49,
      "Communicate the approved change to Floor Staff", "P6", subrow=1,
      ttype="send"),
    N("Task_DeliverOngoingIssues", "task", CM, 50,
      "Complete the case-management admission workflow", "P6", ttype="user",
      doc=["Deliver ongoing contact, behavioral, or consumer-support issues "
           "to the Social Worker or Floor Staff as appropriate."]),
    N("Gateway_HandoffTarget", "gateway_x", CM, 51,
      "Handoff to Floor Staff or Social Worker?", "P6"),
    N("Task_FSReceivesHandoff", "task", FS, 53,
      "Receive handoff of ongoing issues", "P6", subrow=1, ttype="manual"),
    N("Task_SWReceivesHandoff", "task", SW, 54,
      "Receive handoff of ongoing issues", "P6", subrow=2, ttype="manual"),
    N("Gateway_HandoffJoin", "gateway_x", CM, 55,
      "", "P6", subrow=2),
    N("EndEvent_Complete", "end", CM, 56,
      "Case-management admission workflow complete", "P6",
      doc=["The consumer's elopement information, protective-order "
           "restrictions, treatment advocate status, and approved external "
           "contacts are documented and communicated. Required ROI documentation "
           "is placed in the chart. Delayed or unresolved admission activity is "
           "tracked and handed off to Social Worker or Floor Staff."]),
]

EDGES: list[Edge] = [
    E("StartEvent_AdmissionNotification", "Task_BeginElopementForm"),

    E("Task_BeginElopementForm", "Task_ReviewAdmissionReport"),
    E("Task_ReviewAdmissionReport", "Task_SearchOSCN"),
    E("Task_SearchOSCN", "Gateway_ProtectiveOrder"),

    E("Gateway_ProtectiveOrder", "Gateway_ProtectiveOrderJoin", "No"),
    E("Gateway_ProtectiveOrder", "Task_RecordRestrictedPerson", "Yes",
      "Protective order restricts contact"),
    E("Task_RecordRestrictedPerson", "Task_DoNotAuthorizeContact"),
    E("Task_DoNotAuthorizeContact", "Gateway_ConsumerRequestsRestricted"),
    E("Gateway_ConsumerRequestsRestricted", "Gateway_ProtectiveOrderJoin",
      "No"),
    E("Gateway_ConsumerRequestsRestricted", "Task_InformConsumerOfRestriction",
      "Yes", "Consumer requests the restricted contact"),
    E("Task_InformConsumerOfRestriction", "Gateway_ProtectiveOrderJoin"),

    E("Gateway_ProtectiveOrderJoin", "Task_ObtainRemainingInfo"),

    E("Task_ObtainRemainingInfo", "Task_EmailElopementForm"),
    E("Task_EmailElopementForm", "Task_ReviewTAFormWithConsumer"),

    E("Task_ReviewTAFormWithConsumer", "Gateway_ConsumerAbleToParticipate"),
    E("Gateway_ConsumerAbleToParticipate", "Task_ConsumerIdentifiesAdvocate",
      "Yes"),
    E("Gateway_ConsumerAbleToParticipate", "Task_PostponeActivity", "No",
      "Consumer is too agitated, delusional, or unable to participate"),
    E("Task_PostponeActivity", "Task_ReturnWhenAble"),
    E("Task_ReturnWhenAble", "Task_PeriodicFollowUp"),
    E("Task_PeriodicFollowUp", "Task_ReviewTAFormWithConsumer", loop=True),

    E("Task_ConsumerIdentifiesAdvocate", "Task_ContactAdvocate"),
    E("Task_ContactAdvocate", "Task_AdvocateSignsForm"),
    E("Task_AdvocateSignsForm", "Task_ConsumerSignsROI"),
    E("Task_ConsumerSignsROI", "Task_ScanDocumentation"),
    E("Task_ScanDocumentation", "Task_MailCopyToAdvocate"),
    E("Task_MailCopyToAdvocate", "Gateway_AdvocateChangeRequested"),

    E("Gateway_AdvocateChangeRequested", "Gateway_AdvocateChangeJoin", "No"),
    E("Gateway_AdvocateChangeRequested", "Task_ProcessAdvocateChange", "Yes",
      "Consumer requests a different Treatment Advocate"),
    E("Task_ProcessAdvocateChange", "Gateway_AdvocateChangeJoin"),

    E("Gateway_AdvocateChangeJoin", "Task_NursingCompletesAdmission"),

    E("Task_NursingCompletesAdmission", "Task_CheckAdditionalContacts"),

    E("Task_CheckAdditionalContacts", "Gateway_AdditionalContactRequested"),
    E("Gateway_AdditionalContactRequested", "Gateway_ContactJoin", "No"),
    E("Gateway_AdditionalContactRequested", "Task_CompleteROI", "Yes",
      "Consumer requests an additional contact"),
    E("Task_CompleteROI", "Task_RecordROIPurpose"),
    E("Task_RecordROIPurpose", "Task_ContactProspectiveContact"),
    E("Task_ContactProspectiveContact", "Task_ProspectiveContactResponds"),
    E("Task_ProspectiveContactResponds", "Gateway_ContactAgrees"),
    E("Gateway_ContactAgrees", "Task_InformFloorStaffNewContact", "Yes"),
    E("Gateway_ContactAgrees", "Task_InformConsumerDeclined", "No",
      "Prospective Contact declines"),
    E("Task_InformFloorStaffNewContact", "Task_PlaceROIInChartOptionA"),
    E("Task_PlaceROIInChartOptionA", "Gateway_ContactJoin"),
    E("Task_InformConsumerDeclined", "Gateway_ContactJoin"),

    E("Gateway_ContactJoin", "Task_ConfirmContactSheet"),
    E("Task_ConfirmContactSheet", "Task_CommunicateVerifiedContacts"),
    E("Task_CommunicateVerifiedContacts", "Task_FloorStaffMaintainsSheet"),
    E("Task_FloorStaffMaintainsSheet", "Task_FileApprovedROIs"),

    E("Task_FileApprovedROIs", "Gateway_ClinicalEventWitnessed"),
    E("Gateway_ClinicalEventWitnessed", "Gateway_ClinicalEventJoin", "No"),
    E("Gateway_ClinicalEventWitnessed", "Task_DocumentInAvatar", "Yes",
      "Event requires clinical documentation"),
    E("Task_DocumentInAvatar", "Gateway_ClinicalEventJoin"),

    E("Gateway_ClinicalEventJoin", "Gateway_PostAdmissionChange"),
    E("Gateway_PostAdmissionChange", "Task_DeliverOngoingIssues", "No"),
    E("Gateway_PostAdmissionChange", "Task_ProcessContactChange", "Yes",
      "Contact-list change requested after admission"),
    E("Task_ProcessContactChange", "Task_VerifyROIForChange"),
    E("Task_VerifyROIForChange", "Task_CommunicateChangeToFloorStaff"),
    E("Task_CommunicateChangeToFloorStaff", "Gateway_PostAdmissionChange",
      loop=True),

    E("Task_DeliverOngoingIssues", "Gateway_HandoffTarget"),
    E("Gateway_HandoffTarget", "Task_FSReceivesHandoff", "Floor Staff"),
    E("Gateway_HandoffTarget", "Task_SWReceivesHandoff", "Social Worker",
      "Handoff to Social Worker"),
    E("Task_FSReceivesHandoff", "Gateway_HandoffJoin"),
    E("Task_SWReceivesHandoff", "Gateway_HandoffJoin"),

    E("Gateway_HandoffJoin", "EndEvent_Complete"),
]

BY_ID = {n.id: n for n in NODES}

PROCESS_ID = "Process_OFC004"
MAIN_PARTICIPANT = "Participant_OFCCaseManagement"
COLLAB_ID = "Collaboration_OFC004"

PROCESS_DOC = (
    "OFC-004 — Case Manager Intakes Consumer. Oklahoma Forensic Center, "
    "Case Management Unit. Version 1.1, 2026-08-11. Standardized case-management "
    "admission process to establish emergency and restricted contacts, document "
    "the consumer's treatment advocate, verify authorized contacts, and ensure "
    "required release documentation is available to staff."
)


# --------------------------------------------------------------------------
# Layout
# --------------------------------------------------------------------------


def node_size(node: Node) -> tuple[int, int]:
    if node.kind == "task":
        return TASK_W, TASK_H
    if node.kind.startswith("gateway"):
        return GW_W, GW_H
    return EV_W, EV_H


def annotation_height(note: str) -> float:
    lines = -(-len(note) // ANN_CHARS)
    return max(50, lines * ANN_LINE + 18)


def compute_layout() -> dict:
    max_col = max(n.col for n in NODES)
    col_w = [0] * (max_col + 1)
    for n in NODES:
        col_w[n.col] = max(col_w[n.col], node_size(n)[0])

    col_center = []
    x = POOL_X + POOL_HEADER + COL_GAP
    for c in range(max_col + 1):
        col_center.append(x + col_w[c] / 2)
        x += col_w[c] + COL_GAP
    pool_w = x - POOL_X

    base_rows: dict[str, int] = {lid: 1 for lid, _ in LANES}
    for n in NODES:
        base_rows[n.lane] = max(base_rows[n.lane], n.subrow + 1)

    ann_band: dict[str, float] = {lid: 0.0 for lid, _ in LANES}
    for n in NODES:
        if n.note:
            ann_band[n.lane] = max(ann_band[n.lane],
                                   annotation_height(n.note) + 26)

    lane_box: dict[str, tuple[float, float]] = {}
    row_top: dict[str, float] = {}
    ann_center: dict[str, float] = {}
    y = POOL_Y
    for lane_id, _ in LANES:
        band = ann_band[lane_id]
        h = LANE_PAD * 2 + base_rows[lane_id] * ROW_PITCH + band
        lane_box[lane_id] = (y, h)
        if band and lane_id in ANN_ABOVE:
            ann_center[lane_id] = y + LANE_PAD + band / 2
            row_top[lane_id] = y + LANE_PAD + band
        else:
            row_top[lane_id] = y + LANE_PAD
            if band:
                ann_center[lane_id] = (y + LANE_PAD
                                       + base_rows[lane_id] * ROW_PITCH
                                       + band / 2)
        y += h
    pool_h = y - POOL_Y

    def row_center(lane_id: str, subrow: int) -> float:
        return row_top[lane_id] + subrow * ROW_PITCH + ROW_PITCH / 2

    bounds: dict[str, tuple[float, float, float, float]] = {}
    for n in NODES:
        w, h = node_size(n)
        cx = col_center[n.col]
        cy = row_center(n.lane, n.subrow)
        bounds[n.id] = (cx - w / 2, cy - h / 2, w, h)

    ann_bounds: dict[str, tuple[float, float, float, float]] = {}
    for n in NODES:
        if not n.note:
            continue
        h = annotation_height(n.note)
        cx = col_center[n.col]
        cy = ann_center[n.lane]
        ann_bounds[n.id] = (cx - ANN_W / 2, cy - h / 2, ANN_W, h)

    if ann_bounds:
        right = max(x + w for x, _, w, _ in ann_bounds.values())
        pool_w = max(pool_w, right + COL_GAP - POOL_X)

    return {
        "bounds": bounds,
        "ann_bounds": ann_bounds,
        "lane_box": lane_box,
        "row_top": row_top,
        "row_center": row_center,
        "pool": (POOL_X, POOL_Y, pool_w, pool_h),
        "col_center": col_center,
        "offsets": corridor_offsets(),
    }


def corridor_offsets() -> dict[tuple[str, str], float]:
    grouped: dict[str, list[Edge]] = {}
    for e in EDGES:
        if e.loop:
            continue
        if BY_ID[e.source].lane != BY_ID[e.target].lane \
                or BY_ID[e.source].subrow != BY_ID[e.target].subrow:
            grouped.setdefault(e.target, []).append(e)
    out: dict[tuple[str, str], float] = {}
    for target, group in grouped.items():
        for i, e in enumerate(group):
            out[(e.source, target)] = (i - (len(group) - 1) / 2) * 12
    return out


def edge_waypoints(edge: Edge, lay: dict) -> list[tuple[float, float]]:
    src, tgt = BY_ID[edge.source], BY_ID[edge.target]
    sx, sy, sw, sh = lay["bounds"][src.id]
    tx, ty, tw, th = lay["bounds"][tgt.id]
    scy, tcy = sy + sh / 2, ty + th / 2
    scx, tcx = sx + sw / 2, tx + tw / 2

    if edge.loop:
        loop_y = lay["row_top"][src.lane] + (src.subrow + 1) * ROW_PITCH
        return [(scx, sy + sh), (scx, loop_y), (tcx, loop_y), (tcx, ty + th)]

    if abs(scy - tcy) < 1:
        return [(sx + sw, scy), (tx, tcy)]

    corridor = tx - COL_GAP / 2 + lay["offsets"].get((src.id, tgt.id), 0)
    corridor = max(corridor, sx + sw + 10)
    return [(sx + sw, scy), (corridor, scy), (corridor, tcy), (tx, tcy)]


LBL_W, LBL_H = 30, 18


def event_label_bounds(node: Node, x: float, y: float, w: float, h: float,
                       lay: dict) -> tuple[float, float, float, float]:
    centers = lay["col_center"]
    room = []
    if node.col > 0:
        room.append(centers[node.col] - centers[node.col - 1])
    if node.col + 1 < len(centers):
        room.append(centers[node.col + 1] - centers[node.col])
    width = max(70.0, min(110.0, min(room) - 8)) if room else 110.0
    lines = max(1, -(-len(node.name) // max(8, int(width / 6.4))))
    height = lines * 13 + 4

    if node.subrow > 0:
        return (x + w / 2 - width / 2, y - height - 5, width, height)
    return (x + w / 2 - width / 2, y + h + 5, width, height)


def edge_label_bounds(edge: Edge, pts: list[tuple[float, float]],
                      lay: dict) -> tuple[float, float, float, float]:
    src, tgt = BY_ID[edge.source], BY_ID[edge.target]

    if edge.loop:
        mx = (pts[1][0] + pts[2][0]) / 2
        return (mx - LBL_W / 2, pts[1][1] + 3, LBL_W, LBL_H)

    if len(pts) == 2:
        mx = (pts[0][0] + pts[1][0]) / 2
        return (mx - LBL_W / 2, pts[0][1] - LBL_H - 6, LBL_W, LBL_H)

    scy, tcy = pts[0][1], pts[-1][1]
    y = scy + 6 if tcy > scy else scy - LBL_H - 6
    return ((pts[0][0] + pts[1][0]) / 2 - LBL_W / 2, y, LBL_W, LBL_H)


# --------------------------------------------------------------------------
# BPMN XML emitter
# --------------------------------------------------------------------------

NS = {
    "bpmn": "http://www.omg.org/spec/BPMN/20100524/MODEL",
    "bpmndi": "http://www.omg.org/spec/BPMN/20100524/DI",
    "dc": "http://www.omg.org/spec/DD/20100524/DC",
    "di": "http://www.omg.org/spec/DD/20100524/DI",
}
for prefix, uri in NS.items():
    ET.register_namespace(prefix, uri)


def q(prefix: str, tag: str) -> str:
    return f"{{{NS[prefix]}}}{tag}"


TASK_ELEMENT = {
    "manual": "manualTask",
    "user": "userTask",
    "send": "sendTask",
    "receive": "receiveTask",
}


def element_tag(node: Node) -> str:
    if node.kind == "task":
        return TASK_ELEMENT[node.ttype]
    if node.kind == "gateway_x":
        return "exclusiveGateway"
    if node.kind == "gateway_p":
        return "parallelGateway"
    if node.kind == "start_message":
        return "startEvent"
    if node.kind == "end":
        return "endEvent"
    return "intermediateCatchEvent"


def flow_id(edge: Edge) -> str:
    return f"Flow_{edge.source}__{edge.target}"


def add_doc(parent: ET.Element, lines: list[str]) -> None:
    if not lines:
        return
    doc = ET.SubElement(parent, q("bpmn", "documentation"))
    doc.text = "\n".join(f"- {line}" for line in lines)


def build_xml(lay: dict) -> ET.Element:
    defs = ET.Element(q("bpmn", "definitions"), {
        "id": "Definitions_OFC004",
        "targetNamespace": "http://oklahoma.gov/odmhsas/ofc/bpmn",
        "exporter": "generate_bpmn_ofc004.py",
        "exporterVersion": "1.0",
    })

    collab = ET.SubElement(defs, q("bpmn", "collaboration"), {"id": COLLAB_ID})
    ET.SubElement(collab, q("bpmn", "participant"), {
        "id": MAIN_PARTICIPANT,
        "name": "Oklahoma Forensic Center — Case Manager Intakes Consumer",
        "processRef": PROCESS_ID,
    })

    proc = ET.SubElement(defs, q("bpmn", "process"), {
        "id": PROCESS_ID,
        "name": "OFC-004 — Case Manager Intakes Consumer",
        "isExecutable": "false",
    })
    add_doc(proc, [PROCESS_DOC])

    lane_set = ET.SubElement(proc, q("bpmn", "laneSet"),
                             {"id": "LaneSet_OFC004"})
    for lane_id, lane_name in LANES:
        lane = ET.SubElement(lane_set, q("bpmn", "lane"),
                             {"id": lane_id, "name": lane_name})
        for n in NODES:
            if n.lane == lane_id:
                ref = ET.SubElement(lane, q("bpmn", "flowNodeRef"))
                ref.text = n.id

    incoming: dict[str, list[str]] = {n.id: [] for n in NODES}
    outgoing: dict[str, list[str]] = {n.id: [] for n in NODES}
    for e in EDGES:
        outgoing[e.source].append(flow_id(e))
        incoming[e.target].append(flow_id(e))

    defaults: dict[str, str] = {}
    for e in EDGES:
        src = BY_ID[e.source]
        if src.kind == "gateway_x" and len(outgoing[src.id]) > 1 \
                and not e.condition:
            defaults[src.id] = flow_id(e)

    for n in NODES:
        attrs = {"id": n.id}
        if n.name:
            attrs["name"] = n.name
        if n.id in defaults:
            attrs["default"] = defaults[n.id]
        el = ET.SubElement(proc, q("bpmn", element_tag(n)), attrs)
        add_doc(el, n.doc)
        for fid in incoming[n.id]:
            ET.SubElement(el, q("bpmn", "incoming")).text = fid
        for fid in outgoing[n.id]:
            ET.SubElement(el, q("bpmn", "outgoing")).text = fid
        if n.kind == "start_message":
            ET.SubElement(el, q("bpmn", "messageEventDefinition"),
                          {"id": f"MsgDef_{n.id}"})

    for e in EDGES:
        attrs = {
            "id": flow_id(e),
            "sourceRef": e.source,
            "targetRef": e.target,
        }
        if e.label:
            attrs["name"] = e.label
        flow = ET.SubElement(proc, q("bpmn", "sequenceFlow"), attrs)
        if e.condition:
            cond = ET.SubElement(flow, q("bpmn", "conditionExpression"))
            cond.text = e.condition

    for n in NODES:
        if not n.note:
            continue
        ann = ET.SubElement(proc, q("bpmn", "textAnnotation"),
                            {"id": f"Ann_{n.id}"})
        ET.SubElement(ann, q("bpmn", "text")).text = n.note
        ET.SubElement(proc, q("bpmn", "association"), {
            "id": f"Assoc_{n.id}",
            "sourceRef": n.id,
            "targetRef": f"Ann_{n.id}",
        })

    diagram = ET.SubElement(defs, q("bpmndi", "BPMNDiagram"),
                            {"id": "BPMNDiagram_OFC004"})
    plane = ET.SubElement(diagram, q("bpmndi", "BPMNPlane"),
                          {"id": "BPMNPlane_OFC004", "bpmnElement": COLLAB_ID})

    px, py, pw, ph = lay["pool"]

    def shape(bpmn_element: str, x: float, y: float, w: float, h: float,
              *, horizontal: bool | None = None, marker: bool = False,
              label: tuple[float, float, float, float] | None = None) -> None:
        attrs = {
            "id": f"Shape_{bpmn_element}",
            "bpmnElement": bpmn_element,
        }
        if horizontal is not None:
            attrs["isHorizontal"] = "true" if horizontal else "false"
        if marker:
            attrs["isMarkerVisible"] = "true"
        sh = ET.SubElement(plane, q("bpmndi", "BPMNShape"), attrs)
        ET.SubElement(sh, q("dc", "Bounds"), {
            "x": f"{x:.0f}", "y": f"{y:.0f}",
            "width": f"{w:.0f}", "height": f"{h:.0f}",
        })
        if label:
            lbl = ET.SubElement(sh, q("bpmndi", "BPMNLabel"))
            ET.SubElement(lbl, q("dc", "Bounds"), {
                "x": f"{label[0]:.0f}", "y": f"{label[1]:.0f}",
                "width": f"{label[2]:.0f}", "height": f"{label[3]:.0f}",
            })

    shape(MAIN_PARTICIPANT, px, py, pw, ph, horizontal=True)

    for lane_id, _ in LANES:
        top, h = lay["lane_box"][lane_id]
        shape(lane_id, px + POOL_HEADER, top, pw - POOL_HEADER, h,
              horizontal=True)

    for n in NODES:
        x, y, w, h = lay["bounds"][n.id]
        label = None
        if n.name and n.kind in ("start_message", "end"):
            label = event_label_bounds(n, x, y, w, h, lay)
        elif n.name and n.kind.startswith("gateway"):
            lines = max(1, -(-len(n.name) // 21))
            gh = lines * 13 + 4
            label = (x + w / 2 - GW_LBL_W / 2, y - gh - 8, GW_LBL_W, gh)
        shape(n.id, x, y, w, h,
              marker=(n.kind == "gateway_x"), label=label)

    for n in NODES:
        if n.note:
            x, y, w, h = lay["ann_bounds"][n.id]
            shape(f"Ann_{n.id}", x, y, w, h)

    def edge_di(bpmn_element: str, points: list[tuple[float, float]],
                label: tuple[float, float, float, float] | None = None) -> None:
        ed = ET.SubElement(plane, q("bpmndi", "BPMNEdge"), {
            "id": f"Edge_{bpmn_element}",
            "bpmnElement": bpmn_element,
        })
        for wx, wy in points:
            ET.SubElement(ed, q("di", "waypoint"),
                          {"x": f"{wx:.0f}", "y": f"{wy:.0f}"})
        if label:
            lbl = ET.SubElement(ed, q("bpmndi", "BPMNLabel"))
            ET.SubElement(lbl, q("dc", "Bounds"), {
                "x": f"{label[0]:.0f}", "y": f"{label[1]:.0f}",
                "width": f"{label[2]:.0f}", "height": f"{label[3]:.0f}",
            })

    for e in EDGES:
        pts = edge_waypoints(e, lay)
        label = edge_label_bounds(e, pts, lay) if e.label else None
        edge_di(flow_id(e), pts, label)

    for n in NODES:
        if not n.note:
            continue
        nx, ny, nw, nh = lay["bounds"][n.id]
        ax, ay, aw, ah = lay["ann_bounds"][n.id]
        if ay < ny:
            edge_di(f"Assoc_{n.id}", [(nx + nw / 2, ny),
                                      (ax + aw / 2, ay + ah)])
        else:
            edge_di(f"Assoc_{n.id}", [(nx + nw / 2, ny + nh),
                                      (ax + aw / 2, ay)])

    return defs


def write_bpmn(path: Path, lay: dict) -> None:
    raw = ET.tostring(build_xml(lay), encoding="utf-8")
    pretty = minidom.parseString(raw).toprettyxml(indent="  ", encoding="UTF-8")
    text = pretty.decode("utf-8")
    text = "\n".join(line for line in text.splitlines() if line.strip())
    path.write_text(text + "\n", encoding="utf-8")


# --------------------------------------------------------------------------

def main() -> None:
    here = Path(__file__).parent
    lay = compute_layout()

    bpmn_path = here / "OFC-004.bpmn"
    write_bpmn(bpmn_path, lay)

    px, py, pw, ph = lay["pool"]
    tasks = sum(1 for n in NODES if n.kind == "task")
    gws = sum(1 for n in NODES if n.kind.startswith("gateway"))
    evs = len(NODES) - tasks - gws
    print(f"wrote {bpmn_path.name}: {len(NODES)} flow nodes "
          f"({tasks} tasks, {gws} gateways, {evs} events), "
          f"{len(EDGES)} sequence flows, "
          f"{sum(1 for n in NODES if n.note)} annotations")
    print(f"pool bounds: {pw:.0f} x {ph:.0f} px")


if __name__ == "__main__":
    main()
