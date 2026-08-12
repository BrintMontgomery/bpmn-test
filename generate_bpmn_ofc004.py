"""Generate the OFC-004 Case Manager Intakes Consumer BPMN 2.0 diagram.

The process is described once, declaratively, in NODES / EDGES below. This
script computes the diagram layout and emits OFC-004.bpmn — a BPMN 2.0 XML
with full DI, opens in Camunda Modeler, bpmn.io, Signavio, etc.

Source: "OFC-004 — Case Manager Intakes Consumer.md", Main Path and Options.

To change the diagram, edit the model below and re-run this script. Do not
hand-edit OFC-004.bpmn -- it is overwritten.
"""

from __future__ import annotations

from pathlib import Path

from bpmn_engine import (
    E, N, Edge, Node, ProcessModel, Scope,
    compute_layout, write_bpmn,
)

# --------------------------------------------------------------------------
# Process model
# --------------------------------------------------------------------------

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
# Process model data
# --------------------------------------------------------------------------

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
# Shared engine model and entry point
# --------------------------------------------------------------------------

MODEL = ProcessModel(
    lanes=LANES,
    phases=PHASES,
    nodes=NODES,
    edges=EDGES,
    process_id=PROCESS_ID,
    participant_name="Oklahoma Forensic Center — Case Manager Intakes Consumer",
    process_doc=PROCESS_DOC,
    process_name="OFC-004 — Case Manager Intakes Consumer",
    participant_id=MAIN_PARTICIPANT,
    collaboration_id=COLLAB_ID,
    definitions_id="Definitions_OFC004",
    exporter="generate_bpmn_ofc004.py",
    ann_above=ANN_ABOVE,
)

NODES = MODEL.nodes
EDGES = MODEL.edges
LANES = MODEL.lanes
PHASES = MODEL.phases
ANN_ABOVE = MODEL.ann_above
BY_ID = MODEL.by_id()


def main() -> None:
    here = Path(__file__).parent
    scope = Scope.top_level(MODEL)
    lay = compute_layout(MODEL, scope)

    bpmn_path = here / "OFC-004.bpmn"
    write_bpmn(bpmn_path, MODEL, lay, scope)

    px, py, pw, ph = lay.pool or (0, 0, 0, 0)
    tasks = sum(1 for n in MODEL.nodes if n.kind == "task")
    gws = sum(1 for n in MODEL.nodes if n.kind.startswith("gateway"))
    evs = len(MODEL.nodes) - tasks - gws
    print(f"wrote {bpmn_path.name}: {len(MODEL.nodes)} flow nodes "
          f"({tasks} tasks, {gws} gateways, {evs} events), "
          f"{len(MODEL.edges)} sequence flows, "
          f"{sum(1 for n in MODEL.nodes if n.note)} annotations")
    print(f"pool bounds: {pw:.0f} x {ph:.0f} px")


if __name__ == "__main__":
    main()
