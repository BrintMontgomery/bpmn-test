"""Generate the OFC-001 Security Intake BPMN 2.0 diagram.

The process is described once, declaratively, in NODES / EDGES below. This
script computes the diagram layout and emits:

  * OFC-001.bpmn   -- BPMN 2.0 XML with full DI, opens in Camunda Modeler,
                      bpmn.io, Signavio, etc.
  * OFC-001.mmd    -- the same graph as a Mermaid flowchart, for the preview
                      page, so the two can never drift apart.

Source: "OFC-001 - Security Intakes Consumer.md", BPMN Perspective section.

To change the diagram, edit the model below and re-run this script. Do not
hand-edit OFC-001.bpmn -- it is overwritten.
"""

from __future__ import annotations

import re
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
ANN_W = 280           # text annotations wrap to this width
ANN_LINE = 15         # bpmn-js renders annotation text at ~15px per line
ANN_CHARS = 44        # characters that fit on one line at ANN_W

COL_GAP = 78          # horizontal gap between columns; wide enough that a
                      # branch label fits between a gateway and the vertical
                      # corridor that carries the branch to the next row
ROW_PITCH = 150       # vertical distance between sub-rows inside a lane
GW_LBL_W = 140        # explicit label box for a named gateway; the height
                      # is derived from how many lines the name wraps to
LANE_PAD = 15         # padding at top and bottom of every lane
POOL_HEADER = 30      # width of the vertical name band on the left of a pool
POOL_X = 200          # left edge of the main pool
POOL_Y = 260          # top edge of the main pool
AC_POOL_H = 60        # height of the collapsed Admissions Coordinator pool
AC_POOL_W = 320

LANES = [
    ("Lane_SO", "Security Officer"),
    ("Lane_LED", "Law Enforcement Deputy"),
    ("Lane_CON", "Consumer"),
    ("Lane_UN", "Unit Nurse"),
    ("Lane_MHT", "Mental Health Technician"),
]

SO, LED, CON, UN, MHT = (lane_id for lane_id, _ in LANES)

# Lanes whose text-annotation band is placed above their tasks instead of
# below. See compute_layout().
ANN_ABOVE = {SO}

PHASES = [
    ("P0", "Trigger"),
    ("P1", "1. Prepare for Admission"),
    ("P2", "2. Receive Consumer from Law Enforcement"),
    ("P3", "3. Document Transfer of Custody"),
    ("P4", "4. Establish Initial Electronic Admission Record"),
    ("P5", "5. Security Search and Property Inventory"),
    ("P6", "6. ObserveSmart Tracking and Identification"),
    ("P7", "7. Collect Supplemental Admission Information"),
    ("P8", "8. Initiate Nursing Handoff"),
    ("P9", "9. Determine Escort and Nursing Location"),
    ("P10", "10. Complete Shower and Unit Transfer"),
    ("P11", "11. Complete Security-to-Nursing Handoff"),
]


# --------------------------------------------------------------------------
# Model
# --------------------------------------------------------------------------


@dataclass
class Node:
    id: str
    kind: str          # task | gateway_x | gateway_p | start_message
                       # | catch_timer | catch_message | end
    lane: str
    col: int
    name: str
    phase: str
    subrow: int = 0
    ttype: str = "manual"   # manual | user | send | receive (task kinds only)
    doc: list[str] = field(default_factory=list)
    note: str | None = None  # becomes an associated BPMN text annotation


@dataclass
class Edge:
    source: str
    target: str
    label: str = ""
    condition: str = ""      # empty -> this branch is the gateway default
    loop: bool = False       # route backwards, underneath the sub-row


N = Node
E = Edge

NODES: list[Node] = [
    # -- Trigger ----------------------------------------------------------
    N("StartEvent_ScheduledAdmission", "start_message", SO, 0,
      "Scheduled admission email received", "P0",
      doc=["Receive the consumer name, identifying number, destination unit, "
           "and planned admission date from the Admissions Coordinator."]),
    N("Event_DayOfAdmission", "catch_timer", SO, 1,
      "On the day of admission", "P0",
      doc=["The packet is prepared on the day of admission, not on receipt "
           "of the scheduling email."]),

    # -- 1. Prepare for Admission -----------------------------------------
    N("Task_ReviewSchedule", "task", SO, 2,
      "Review admission schedule and confirm admission remains active",
      "P1", ttype="user",
      doc=["Review the admission schedule on the day of admission.",
           "Confirm that the scheduled admission remains active."]),
    N("Gateway_InfoChanged", "gateway_x", SO, 3,
      "Admission information changed?", "P1",
      doc=["Option B - the admission date, arrival time, consumer "
           "information, or destination unit changed before arrival."]),
    N("Task_PreparePacket", "task", SO, 4,
      "Prepare the security admission packet", "P1",
      doc=["Prepare the security admission packet on the day of admission.",
           "Enter the consumer name, identifying number, and destination "
           "unit on each applicable page."],
      note="[a] Prepare the packet on the day of admission because "
           "admission dates and times are frequently changed. Do not print "
           "the final packet solely in response to the initial scheduling "
           "email."),
    N("Task_ReviewLatestEmail", "task", SO, 4,
      "Review the most recent admission email", "P1", subrow=1, ttype="user",
      doc=["Review the most recent admission email.",
           "Confirm the current admission date, arrival time, consumer "
           "information, and destination unit.",
           "Do not rely on a packet printed from an earlier schedule."]),
    N("Task_UpdatePacket", "task", SO, 5,
      "Print or update the packet from confirmed information",
      "P1", subrow=1,
      doc=["Print or update the security admission packet using the "
           "confirmed information."]),
    N("Gateway_InfoChangedJoin", "gateway_x", SO, 6,
      "", "P1",
      doc=["Resume admission preparation using the current confirmed "
           "admission information."]),
    N("Task_VerifyReadiness", "task", SO, 7,
      "Verify packet contents, system access, and staffing", "P1",
      doc=["Confirm the packet contains the Vendor Form, the Admission "
           "Property Inventory, the Admission Notification Form, and the "
           "Security Intake Questionnaire.",
           "Confirm active Avatar access and active ObserveSmart access.",
           "Confirm that the tablet is functioning.",
           "Confirm that an ObserveSmart beacon is available.",
           "Confirm that the camera and ID-bracelet equipment are available.",
           "Confirm that at least two Security Officers are available for "
           "the security search."]),
    N("Task_StageEquipment", "task", SO, 8,
      "Stage admission systems and equipment", "P1",
      doc=["Stage Avatar, ObserveSmart, the tablet, the beacon, the camera, "
           "and the ID-bracelet equipment."]),

    # -- 2. Receive Consumer from Law Enforcement -------------------------
    N("Task_AnnounceArrival", "task", LED, 9,
      "Announce arrival through the sally-port intercom", "P2"),
    N("Gateway_UnscheduledArrival", "gateway_x", SO, 10,
      "Arrival unscheduled or outside the expected time?", "P2",
      doc=["Option A - the Law Enforcement Deputy arrives without calling "
           "ahead or arrives outside the scheduled time."]),
    N("Task_VerifyAgainstSchedule", "task", SO, 11,
      "Verify consumer against the schedule and daily plan",
      "P2", subrow=1, ttype="user",
      doc=["Verify the consumer against the scheduled admission email and "
           "the daily admission plan.",
           "Confirm that the admission remains authorized."]),
    N("Task_UpdatePacketOnArrival", "task", SO, 12,
      "Prepare or update the packet and stage equipment", "P2", subrow=1,
      doc=["Prepare or update the admission packet after confirming the "
           "admission.",
           "Stage the required admission systems and equipment."]),
    N("Gateway_UnscheduledArrivalJoin", "gateway_x", SO, 13,
      "", "P2",
      doc=["Resume the standard arrival process after confirming the "
           "admission."]),
    N("Task_AdmitVehicle", "task", SO, 14,
      "Admit the transport vehicle and close the garage door", "P2",
      doc=["Admit the transport vehicle into the sally port.",
           "Close the garage door."]),
    N("Task_EscortToHolding", "task", LED, 15,
      "Remove consumer from the vehicle and escort to the holding room",
      "P2",
      doc=["Remove the consumer from the transport vehicle.",
           "Escort the consumer to the admissions holding room."]),
    N("Task_RemoveShackles", "task", LED, 16,
      "Remove the consumer's shackles in the holding room", "P2"),
    N("Task_ObtainReport", "task", SO, 17,
      "Obtain the behavioral and transport report from the Deputy", "P2",
      doc=["Review conduct at the county facility.",
           "Review any combative incidents or transport problems.",
           "Review any reported threats, agitation, or other safety "
           "concerns."],
      note="[b] The behavioral report should address conduct at the county "
           "facility, combative incidents, problems during transport, "
           "threats, agitation, and other facts that affect staffing or "
           "safety precautions."),
    N("Gateway_SafetyConcern", "gateway_x", SO, 18,
      "Behavioral or safety concern?", "P2",
      doc=["Option C - the Deputy reports combative behavior, transport "
           "problems, threats, or other safety concerns, or the consumer "
           "appears irritable, agitated, or verbally aggressive."]),
    N("Task_RecordBehavioralInfo", "task", SO, 19,
      "Record the behavioral and safety information", "P2", subrow=1,
      ttype="user"),
    N("Task_CallUnitEarly", "task", SO, 20,
      "Call the destination unit and request a nursing assessment",
      "P2", subrow=1, ttype="send",
      doc=["Call the destination unit before continuing routine processing.",
           "Report the identified behavioral or safety concern.",
           "Request a nursing assessment."]),
    N("Task_NurseAssess", "task", UN, 21,
      "Report to admissions and assess the consumer", "P2",
      doc=["Report to the admissions area.",
           "Assess the consumer.",
           "Determine whether clinical intervention is required."]),
    N("Gateway_ClinicalIntervention", "gateway_x", UN, 22,
      "Clinical intervention required?", "P2"),
    N("Task_AdjustPrecautions", "task", SO, 23,
      "Adjust staffing and movement precautions", "P2", subrow=1,
      doc=["Adjust security staffing and movement precautions according to "
           "the nursing assessment."]),
    N("Event_NurseAuthorizes", "catch_message", SO, 24,
      "Unit Nurse authorizes continuation", "P2", subrow=1),
    N("Gateway_ClinicalInterventionJoin", "gateway_x", SO, 25,
      "", "P2", subrow=1),
    N("Gateway_SafetyConcernJoin", "gateway_x", SO, 26,
      "", "P2",
      doc=["Resume routine security admission when the Unit Nurse "
           "authorizes continuation."]),

    # -- 3. Document Transfer of Custody ----------------------------------
    N("Task_DeputySignsForm", "task", LED, 27,
      "Sign the Admission Notification Form before departure", "P3",
      note="[f] The Law Enforcement Deputy must sign the Admission "
           "Notification Form before departing. Do not release the deputy "
           "until the form has been signed, copied, and returned."),
    N("Task_OfficerSignsAndCopies", "task", SO, 28,
      "Sign the Admission Notification Form and make the required copies",
      "P3"),
    N("Task_GiveCopyToDeputy", "task", SO, 29,
      "Give one copy of the form to the Law Enforcement Deputy", "P3"),
    N("Gateway_CustodyDocsComplete", "gateway_x", SO, 30,
      "Form signed, copied, and returned?", "P3"),
    N("Task_ReleaseDeputy", "task", SO, 31,
      "Release the Law Enforcement Deputy", "P3",
      doc=["Release the Deputy after the transfer-of-custody documentation "
           "is complete."]),

    # -- 4. Establish Initial Electronic Admission Record -----------------
    N("Task_EnterAvatarInitial", "task", SO, 32,
      "Enter known admission information into Avatar", "P4", ttype="user",
      doc=["Record the consumer's language.",
           "Record the transporting authority.",
           "Record the admitting clinician.",
           "Record the originating county."]),

    # -- 5. Security Search and Property Inventory ------------------------
    N("Task_SecuritySearch", "task", SO, 33,
      "Conduct the two-officer security search", "P5",
      doc=["Assign two Security Officers to conduct the security search.",
           "Search the consumer for contraband.",
           "Search the consumer for hidden instruments.",
           "Identify personal property discovered during the search."],
      note="[c] Current security practice uses two Security Officers for "
           "the search of one consumer. Security staffing should exceed the "
           "number of consumers being searched whenever operationally "
           "possible."),
    N("Task_RecordProperty", "task", SO, 34,
      "Record the consumer's property on the Admission Property Inventory",
      "P5", ttype="user"),
    N("Task_ConsumerDresses", "task", CON, 35,
      "Dress after the security search is complete", "P5"),

    # -- 6. ObserveSmart Tracking and Identification ----------------------
    N("Task_ObserveSmartEntry", "task", SO, 36,
      "Enter the consumer into ObserveSmart and pair the beacon",
      "P6", ttype="user",
      doc=["Enter the consumer's name into ObserveSmart.",
           "Enter the consumer's date of birth into ObserveSmart.",
           "Enter the consumer's destination unit into ObserveSmart.",
           "Pair the assigned ObserveSmart beacon with the consumer."],
      note="[d] ObserveSmart is the tracking system used for the consumer's "
           "beacon and subsequent observation checks. The beacon must be "
           "paired to the correct consumer before it is placed on the "
           "consumer."),
    N("Task_CapturePhoto", "task", SO, 37,
      "Capture the consumer's photograph", "P6",
      doc=["Capture the consumer's photograph for the facility record.",
           "Associate the photograph with the ObserveSmart record."]),
    N("Gateway_BeaconVerified", "gateway_x", SO, 38,
      "Beacon paired to the correct consumer?", "P6"),
    N("Task_PlaceBeacon", "task", SO, 39,
      "Place the paired beacon on the consumer", "P6"),

    # -- 7. Collect Supplemental Admission Information --------------------
    N("Task_IntakeQuestionnaire", "task", SO, 40,
      "Collect supplemental information using the Security Intake "
      "Questionnaire", "P7", ttype="user",
      doc=["Record military-service status.",
           "Record allergy information.",
           "Record state of birth.",
           "Record marital history.",
           "Record emergency-contact information."],
      note="[e] The Security Intake Questionnaire is a local reference "
           "document and is not an official OFC form. Use it to collect "
           "information required for Avatar, but do not treat it as the "
           "official electronic record."),
    N("Task_SignVendorForm", "task", CON, 41,
      "Sign the Vendor Form", "P7",
      note="[h] The Vendor Form supports the return or payment of consumer "
           "funds at discharge, usually by check. It sets the consumer up "
           "in the finance system so OFC can pay out any remaining funds "
           "when they leave."),
    N("Task_ReturnToHolding", "task", SO, 42,
      "Return the consumer to the holding room", "P7"),
    N("Task_CompleteAvatar", "task", SO, 43,
      "Complete the remaining Avatar fields", "P7", ttype="user",
      doc=["Use the best available information from the admission documents "
           "and the consumer interview."]),
    N("Task_CreateBracelet", "task", SO, 44,
      "Create the ID bracelet from the admission photograph", "P7"),
    N("Task_PlaceBracelet", "task", SO, 45,
      "Place the ID bracelet on the consumer", "P7"),

    # -- 8. Initiate Nursing Handoff --------------------------------------
    N("Task_CallUnitReady", "task", SO, 46,
      "Call the destination unit and report the consumer is ready",
      "P8", ttype="send",
      doc=["Call the destination unit.",
           "Report that the consumer is ready for the nursing admission "
           "process."]),
    N("Event_StaffArrive", "catch_message", SO, 47,
      "Unit Nurse and Mental Health Technician report to admissions", "P8",
      doc=["Hold the consumer in the admissions area until the Unit Nurse "
           "and Mental Health Technician report."]),
    N("Gateway_NursingSplit", "gateway_p", SO, 48, "", "P8"),
    N("Task_LiceTreatment", "task", UN, 49,
      "Apply the required lice treatment", "P8"),
    N("Task_RecordIntakeNeeds", "task", MHT, 49,
      "Record clothing size, allergies, and immediate food needs",
      "P8", ttype="user",
      doc=["Record the consumer's clothing size.",
           "Record the consumer's allergies.",
           "Record the consumer's hunger status.",
           "Record any immediate food needs."]),
    N("Gateway_NursingJoin", "gateway_p", SO, 50, "", "P8"),

    # -- 9. Determine Escort and Nursing Location -------------------------
    N("Gateway_EscortConstraints", "gateway_x", SO, 51,
      "Multiple admissions or escort constraints?", "P9",
      doc=["Option D - Security is processing multiple admissions or the "
           "primary Security Officer cannot complete the shower or unit "
           "escort."]),
    N("Task_StandardEscort", "task", SO, 52,
      "Use the standard Security Officer and MHT escort", "P9"),
    N("Task_CoordinateEscort", "task", SO, 52,
      "Coordinate the escort plan with the Unit Nurse and MHT",
      "P9", subrow=1,
      doc=["Assign a Security Officer to support the escort when staffing "
           "permits.",
           "Assign the Mental Health Technician to perform or assist with "
           "the escort according to staffing and unit direction."]),
    N("Gateway_EscortConstraintsJoin", "gateway_x", SO, 53,
      "", "P9",
      doc=["Resume consumer movement under the established escort plan."]),
    N("Gateway_AltLocation", "gateway_x", SO, 54,
      "Alternate shower or nursing location required?", "P9",
      doc=["Option E - the destination unit directs that the shower or "
           "nursing admission activities occur in a secure unit location "
           "rather than the admissions-area shower."]),
    N("Task_EscortToShower", "task", SO, 55,
      "Escort the consumer to the admissions-area shower", "P9"),
    N("Task_EscortToAltLocation", "task", SO, 55,
      "Escort the consumer to the location designated by the Unit Nurse",
      "P9", subrow=1),
    N("Task_NursingAtAltLocation", "task", UN, 57,
      "Complete the required nursing activities at the designated location",
      "P9"),

    # -- 10. Complete Shower and Unit Transfer ----------------------------
    N("Task_Shower", "task", CON, 56,
      "Complete the shower under required supervision", "P10",
      doc=["The shower is completed under the required security and "
           "clinical supervision."]),
    N("Task_EscortToUnit", "task", SO, 57,
      "Escort the consumer to the destination unit", "P10",
      doc=["The Security Officer and Mental Health Technician escort the "
           "consumer from the shower location to the destination unit."]),
    N("Gateway_LocationJoin", "gateway_x", SO, 58,
      "", "P10",
      doc=["Resume the common handoff flow when the consumer reaches the "
           "location where the Unit Nurse will accept custody."]),

    # -- 11. Complete Security-to-Nursing Handoff -------------------------
    N("Task_NurseAccepts", "task", UN, 59,
      "Accept the consumer and complete the security-to-nursing handoff",
      "P11",
      doc=["The consumer is presented to the Unit Nurse at the destination "
           "unit or authorized alternate location.",
           "Confirm receipt of the consumer.",
           "Complete the security-to-nursing handoff."]),
    N("EndEvent_Complete", "end", SO, 60,
      "Security admission complete", "P11",
      doc=["The consumer has been accepted from law enforcement.",
           "The security search and property documentation are complete.",
           "Required transfer-of-custody forms and signatures are complete.",
           "The consumer has been entered into Avatar.",
           "The ObserveSmart beacon has been paired and placed.",
           "The consumer photograph and ID bracelet are complete.",
           "The Unit Nurse has accepted the consumer."],
      note="[g] The security admission process ends when the consumer "
           "reaches the destination unit and the Unit Nurse accepts the "
           "handoff. Nursing assessment, social-work admission, "
           "case-management admission, treatment, and discharge are outside "
           "the scope of this OC."),
]

EDGES: list[Edge] = [
    E("StartEvent_ScheduledAdmission", "Event_DayOfAdmission"),
    E("Event_DayOfAdmission", "Task_ReviewSchedule"),
    E("Task_ReviewSchedule", "Gateway_InfoChanged"),

    E("Gateway_InfoChanged", "Task_PreparePacket", "No"),
    E("Gateway_InfoChanged", "Task_ReviewLatestEmail", "Yes",
      "Admission date, time, consumer information, or destination unit "
      "changed"),
    E("Task_ReviewLatestEmail", "Task_UpdatePacket"),
    E("Task_PreparePacket", "Gateway_InfoChangedJoin"),
    E("Task_UpdatePacket", "Gateway_InfoChangedJoin"),
    E("Gateway_InfoChangedJoin", "Task_VerifyReadiness"),
    E("Task_VerifyReadiness", "Task_StageEquipment"),
    E("Task_StageEquipment", "Task_AnnounceArrival"),

    E("Task_AnnounceArrival", "Gateway_UnscheduledArrival"),
    E("Gateway_UnscheduledArrival", "Gateway_UnscheduledArrivalJoin", "No"),
    E("Gateway_UnscheduledArrival", "Task_VerifyAgainstSchedule", "Yes",
      "Deputy arrived without calling ahead or outside the scheduled time"),
    E("Task_VerifyAgainstSchedule", "Task_UpdatePacketOnArrival"),
    E("Task_UpdatePacketOnArrival", "Gateway_UnscheduledArrivalJoin"),
    E("Gateway_UnscheduledArrivalJoin", "Task_AdmitVehicle"),
    E("Task_AdmitVehicle", "Task_EscortToHolding"),
    E("Task_EscortToHolding", "Task_RemoveShackles"),
    E("Task_RemoveShackles", "Task_ObtainReport"),

    E("Task_ObtainReport", "Gateway_SafetyConcern"),
    E("Gateway_SafetyConcern", "Gateway_SafetyConcernJoin", "No"),
    E("Gateway_SafetyConcern", "Task_RecordBehavioralInfo", "Yes",
      "Combative behavior, transport problems, threats, agitation, or "
      "other safety concern reported"),
    E("Task_RecordBehavioralInfo", "Task_CallUnitEarly"),
    E("Task_CallUnitEarly", "Task_NurseAssess"),
    E("Task_NurseAssess", "Gateway_ClinicalIntervention"),
    E("Gateway_ClinicalIntervention", "Gateway_ClinicalInterventionJoin",
      "No"),
    E("Gateway_ClinicalIntervention", "Task_AdjustPrecautions", "Yes",
      "Nursing assessment requires clinical intervention"),
    E("Task_AdjustPrecautions", "Event_NurseAuthorizes"),
    E("Event_NurseAuthorizes", "Gateway_ClinicalInterventionJoin"),
    E("Gateway_ClinicalInterventionJoin", "Gateway_SafetyConcernJoin"),

    E("Gateway_SafetyConcernJoin", "Task_DeputySignsForm"),
    E("Task_DeputySignsForm", "Task_OfficerSignsAndCopies"),
    E("Task_OfficerSignsAndCopies", "Task_GiveCopyToDeputy"),
    E("Task_GiveCopyToDeputy", "Gateway_CustodyDocsComplete"),
    E("Gateway_CustodyDocsComplete", "Task_ReleaseDeputy", "Yes"),
    E("Gateway_CustodyDocsComplete", "Task_OfficerSignsAndCopies", "No",
      "Form not yet signed, copied, and returned", loop=True),
    E("Task_ReleaseDeputy", "Task_EnterAvatarInitial"),

    E("Task_EnterAvatarInitial", "Task_SecuritySearch"),
    E("Task_SecuritySearch", "Task_RecordProperty"),
    E("Task_RecordProperty", "Task_ConsumerDresses"),
    E("Task_ConsumerDresses", "Task_ObserveSmartEntry"),

    E("Task_ObserveSmartEntry", "Task_CapturePhoto"),
    E("Task_CapturePhoto", "Gateway_BeaconVerified"),
    E("Gateway_BeaconVerified", "Task_PlaceBeacon", "Yes"),
    E("Gateway_BeaconVerified", "Task_ObserveSmartEntry", "No",
      "Beacon is not paired to the correct consumer", loop=True),
    E("Task_PlaceBeacon", "Task_IntakeQuestionnaire"),

    E("Task_IntakeQuestionnaire", "Task_SignVendorForm"),
    E("Task_SignVendorForm", "Task_ReturnToHolding"),
    E("Task_ReturnToHolding", "Task_CompleteAvatar"),
    E("Task_CompleteAvatar", "Task_CreateBracelet"),
    E("Task_CreateBracelet", "Task_PlaceBracelet"),
    E("Task_PlaceBracelet", "Task_CallUnitReady"),

    E("Task_CallUnitReady", "Event_StaffArrive"),
    E("Event_StaffArrive", "Gateway_NursingSplit"),
    E("Gateway_NursingSplit", "Task_LiceTreatment"),
    E("Gateway_NursingSplit", "Task_RecordIntakeNeeds"),
    E("Task_LiceTreatment", "Gateway_NursingJoin"),
    E("Task_RecordIntakeNeeds", "Gateway_NursingJoin"),

    E("Gateway_NursingJoin", "Gateway_EscortConstraints"),
    E("Gateway_EscortConstraints", "Task_StandardEscort", "No"),
    E("Gateway_EscortConstraints", "Task_CoordinateEscort", "Yes",
      "Multiple admissions in progress or the primary officer cannot "
      "complete the escort"),
    E("Task_StandardEscort", "Gateway_EscortConstraintsJoin"),
    E("Task_CoordinateEscort", "Gateway_EscortConstraintsJoin"),
    E("Gateway_EscortConstraintsJoin", "Gateway_AltLocation"),

    E("Gateway_AltLocation", "Task_EscortToShower", "No"),
    E("Gateway_AltLocation", "Task_EscortToAltLocation", "Yes",
      "Destination unit directs a secure unit location instead of the "
      "admissions-area shower"),
    E("Task_EscortToAltLocation", "Task_NursingAtAltLocation"),
    E("Task_NursingAtAltLocation", "Gateway_LocationJoin"),
    E("Task_EscortToShower", "Task_Shower"),
    E("Task_Shower", "Task_EscortToUnit"),
    E("Task_EscortToUnit", "Gateway_LocationJoin"),

    E("Gateway_LocationJoin", "Task_NurseAccepts"),
    E("Task_NurseAccepts", "EndEvent_Complete"),
]

# Collapsed external pool + the message that starts the process.
AC_PARTICIPANT = "Participant_AdmissionsCoordinator"
AC_MESSAGE_FLOW = "MessageFlow_ScheduledAdmission"

PROCESS_ID = "Process_OFC001"
MAIN_PARTICIPANT = "Participant_OFCSecurityIntake"
COLLAB_ID = "Collaboration_OFC001"

PROCESS_DOC = (
    "OFC-001 - Security Intakes Consumer. Oklahoma Forensic Center, "
    "Security Unit. Version 1.1, 2026-08-11. Controlled process for "
    "receiving a consumer from law enforcement, documenting the transfer of "
    "custody, completing security screening and identification, "
    "establishing electronic tracking, and handing the consumer to nursing "
    "staff."
)

BY_ID = {n.id: n for n in NODES}


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
    """Tall enough that bpmn-js's wrapped text stays inside the bracket."""
    lines = -(-len(note) // ANN_CHARS)        # ceiling division
    return max(50, lines * ANN_LINE + 18)


def compute_layout() -> dict:
    """Assign an absolute (x, y, w, h) to every node, lane, and pool."""
    # Column widths are driven by the widest element in each column, so
    # gateway-only and event-only columns stay narrow.
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

    # A lane is tall enough for its deepest sub-row, plus one extra sub-row
    # for text annotations when the lane carries any. The Security Officer
    # lane takes its annotation band above its tasks rather than below:
    # every edge arriving from a lower lane climbs into that lane, and a
    # band underneath would sit directly in the path.
    base_rows: dict[str, int] = {lid: 1 for lid, _ in LANES}
    for n in NODES:
        base_rows[n.lane] = max(base_rows[n.lane], n.subrow + 1)

    # The annotation band is sized by the tallest note in the lane.
    ann_band: dict[str, float] = {lid: 0.0 for lid, _ in LANES}
    for n in NODES:
        if n.note:
            ann_band[n.lane] = max(ann_band[n.lane],
                                   annotation_height(n.note) + 26)

    lane_box: dict[str, tuple[float, float]] = {}   # lane -> (top, height)
    row_top: dict[str, float] = {}                  # lane -> y of sub-row 0
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

    # Text annotations sit in their lane's reserved band.
    ann_bounds: dict[str, tuple[float, float, float, float]] = {}
    for n in NODES:
        if not n.note:
            continue
        h = annotation_height(n.note)
        cx = col_center[n.col]
        cy = ann_center[n.lane]
        ann_bounds[n.id] = (cx - ANN_W / 2, cy - h / 2, ANN_W, h)

    # A wide annotation on a narrow trailing column can overhang the pool.
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
    """Stagger the vertical run of edges that converge on the same target.

    Two branches joining one gateway from different lanes would otherwise
    drop down the exact same x and render as a single line.
    """
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
        # Route backwards underneath the source sub-row, along the empty
        # boundary the layout leaves between sub-rows.
        loop_y = lay["row_top"][src.lane] + (src.subrow + 1) * ROW_PITCH
        return [(scx, sy + sh), (scx, loop_y), (tcx, loop_y), (tcx, ty + th)]

    if abs(scy - tcy) < 1:
        return [(sx + sw, scy), (tx, tcy)]

    # Orthogonal dog-leg. The long horizontal run stays on the source's own
    # sub-row -- where the layout guarantees a clear span, since the source
    # is what occupies that row -- and the vertical run drops through the
    # empty column gap immediately before the target.
    corridor = tx - COL_GAP / 2 + lay["offsets"].get((src.id, tgt.id), 0)
    corridor = max(corridor, sx + sw + 10)
    return [(sx + sw, scy), (corridor, scy), (corridor, tcy), (tx, tcy)]


LBL_W, LBL_H = 30, 18


def event_label_bounds(node: Node, x: float, y: float, w: float, h: float,
                       lay: dict) -> tuple[float, float, float, float]:
    """An event's caption is wider than the event itself, so it has to fit
    the space between neighbouring columns or it collides with the caption
    next door."""
    centers = lay["col_center"]
    room = []
    if node.col > 0:
        room.append(centers[node.col] - centers[node.col - 1])
    if node.col + 1 < len(centers):
        room.append(centers[node.col + 1] - centers[node.col])
    width = max(70.0, min(110.0, min(room) - 8)) if room else 110.0
    lines = max(1, -(-len(node.name) // max(8, int(width / 6.4))))
    height = lines * 13 + 4

    # On a branch sub-row the space below carries return traffic, so the
    # caption goes above the event instead.
    if node.subrow > 0:
        return (x + w / 2 - width / 2, y - height - 5, width, height)
    return (x + w / 2 - width / 2, y + h + 5, width, height)


def edge_label_bounds(edge: Edge, pts: list[tuple[float, float]],
                      lay: dict) -> tuple[float, float, float, float]:
    """Both branches of a gateway leave from the same edge of the same
    shape, so anchoring every label to the first waypoint stacks them on
    top of each other. Place each label on the segment that distinguishes
    the branch instead."""
    src, tgt = BY_ID[edge.source], BY_ID[edge.target]

    if edge.loop:
        # On the return run, below the line.
        mx = (pts[1][0] + pts[2][0]) / 2
        return (mx - LBL_W / 2, pts[1][1] + 3, LBL_W, LBL_H)

    if len(pts) == 2:
        # Straight through: centred above the connector.
        mx = (pts[0][0] + pts[1][0]) / 2
        return (mx - LBL_W / 2, pts[0][1] - LBL_H - 6, LBL_W, LBL_H)

    # Dog-leg: on the side the branch turns towards, centred in the clear
    # span between the source and the vertical corridor -- clear of the
    # source shape, of the corridor, and of whatever the branch bypasses.
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
        "id": "Definitions_OFC001",
        "targetNamespace": "http://oklahoma.gov/odmhsas/ofc/bpmn",
        "exporter": "generate_bpmn.py",
        "exporterVersion": "1.0",
    })

    # -- collaboration ----------------------------------------------------
    collab = ET.SubElement(defs, q("bpmn", "collaboration"), {"id": COLLAB_ID})
    ET.SubElement(collab, q("bpmn", "participant"), {
        "id": AC_PARTICIPANT,
        "name": "Admissions Coordinator",
    })
    ET.SubElement(collab, q("bpmn", "participant"), {
        "id": MAIN_PARTICIPANT,
        "name": "Oklahoma Forensic Center — Security Intake",
        "processRef": PROCESS_ID,
    })
    ET.SubElement(collab, q("bpmn", "messageFlow"), {
        "id": AC_MESSAGE_FLOW,
        "name": "Scheduled admission email",
        "sourceRef": AC_PARTICIPANT,
        "targetRef": "StartEvent_ScheduledAdmission",
    })

    # -- process ----------------------------------------------------------
    proc = ET.SubElement(defs, q("bpmn", "process"), {
        "id": PROCESS_ID,
        "name": "OFC-001 — Security Intakes Consumer",
        "isExecutable": "false",
    })
    add_doc(proc, [PROCESS_DOC])

    lane_set = ET.SubElement(proc, q("bpmn", "laneSet"),
                             {"id": "LaneSet_OFC001"})
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

    # An exclusive gateway's unconditioned branch is its default flow.
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
        if n.kind == "start_message" or n.kind == "catch_message":
            ET.SubElement(el, q("bpmn", "messageEventDefinition"),
                          {"id": f"MsgDef_{n.id}"})
        elif n.kind == "catch_timer":
            timer = ET.SubElement(el, q("bpmn", "timerEventDefinition"),
                                  {"id": f"TimerDef_{n.id}"})
            date = ET.SubElement(timer, q("bpmn", "timeDate"))
            date.text = "Day of the scheduled admission"

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

    # -- text annotations -------------------------------------------------
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

    # -- diagram interchange ----------------------------------------------
    diagram = ET.SubElement(defs, q("bpmndi", "BPMNDiagram"),
                            {"id": "BPMNDiagram_OFC001"})
    plane = ET.SubElement(diagram, q("bpmndi", "BPMNPlane"),
                          {"id": "BPMNPlane_OFC001", "bpmnElement": COLLAB_ID})

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

    # Collapsed Admissions Coordinator pool, centred over the start event.
    sx, sy, sw, sh_ = lay["bounds"]["StartEvent_ScheduledAdmission"]
    ac_x = sx + sw / 2 - AC_POOL_W / 2
    ac_y = POOL_Y - AC_POOL_H - 110
    shape(AC_PARTICIPANT, ac_x, ac_y, AC_POOL_W, AC_POOL_H, horizontal=True)
    shape(MAIN_PARTICIPANT, px, py, pw, ph, horizontal=True)

    for lane_id, _ in LANES:
        top, h = lay["lane_box"][lane_id]
        shape(lane_id, px + POOL_HEADER, top, pw - POOL_HEADER, h,
              horizontal=True)

    for n in NODES:
        x, y, w, h = lay["bounds"][n.id]
        label = None
        if n.name and n.kind in ("start_message", "end", "catch_timer",
                                 "catch_message"):
            label = event_label_bounds(n, x, y, w, h, lay)
        elif n.name and n.kind.startswith("gateway"):
            # Above the diamond, not below: below is where the branch
            # labels sit and where a loop-back connector runs.
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

    # Message flow from the collapsed pool down into the start event.
    edge_di(AC_MESSAGE_FLOW, [
        (ac_x + AC_POOL_W / 2, ac_y + AC_POOL_H),
        (ac_x + AC_POOL_W / 2, sy),
    ], label=(ac_x + AC_POOL_W / 2 + 6, ac_y + AC_POOL_H + 22, 140, 27))

    for e in EDGES:
        pts = edge_waypoints(e, lay)
        label = edge_label_bounds(e, pts, lay) if e.label else None
        edge_di(flow_id(e), pts, label)

    for n in NODES:
        if not n.note:
            continue
        nx, ny, nw, nh = lay["bounds"][n.id]
        ax, ay, aw, ah = lay["ann_bounds"][n.id]
        if ay < ny:     # annotation band sits above the task
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
# Mermaid emitter -- same graph, for the preview page
# --------------------------------------------------------------------------

LANE_CLASS = {
    SO: "so", LED: "led", CON: "con", UN: "un", MHT: "mht",
}


def mermaid_label(text: str) -> str:
    """Mermaid chokes on quotes, brackets and parentheses inside labels."""
    text = text.replace('"', "'")
    text = re.sub(r"[\[\]{}()<>|]", "", text)
    return text


def wrap(text: str, width: int = 26) -> str:
    words, lines, cur = text.split(), [], ""
    for w in words:
        if cur and len(cur) + 1 + len(w) > width:
            lines.append(cur)
            cur = w
        else:
            cur = f"{cur} {w}".strip()
    if cur:
        lines.append(cur)
    return "<br/>".join(lines)


def mermaid_node(n: Node) -> str:
    if n.kind.startswith("gateway"):
        label = n.name or ("Merge" if n.kind == "gateway_x" else "Join")
        return f'{n.id}{{"{wrap(mermaid_label(label), 20)}"}}'
    if n.kind in ("start_message", "end", "catch_timer", "catch_message"):
        return f'{n.id}(["{wrap(mermaid_label(n.name), 24)}"])'
    return f'{n.id}["{wrap(mermaid_label(n.name))}"]'


def build_mermaid() -> str:
    out = ["flowchart TB"]
    phase_names = dict(PHASES)
    for phase_id, phase_name in PHASES:
        members = [n for n in NODES if n.phase == phase_id]
        if not members:
            continue
        out.append(f'  subgraph {phase_id}["{phase_names[phase_id]}"]')
        out.append("    direction LR")
        for n in members:
            out.append(f"    {mermaid_node(n)}")
        out.append("  end")

    out.append("  AC([Admissions Coordinator]):::ext")
    out.append("  AC -. scheduled admission email .-> "
               "StartEvent_ScheduledAdmission")
    for e in EDGES:
        if e.label:
            out.append(f"  {e.source} -->|{mermaid_label(e.label)}| "
                       f"{e.target}")
        else:
            out.append(f"  {e.source} --> {e.target}")

    out += [
        "  classDef so fill:#dbeafe,stroke:#1d4ed8,color:#0f172a;",
        "  classDef led fill:#fee2e2,stroke:#b91c1c,color:#0f172a;",
        "  classDef con fill:#fef3c7,stroke:#b45309,color:#0f172a;",
        "  classDef un fill:#dcfce7,stroke:#15803d,color:#0f172a;",
        "  classDef mht fill:#f3e8ff,stroke:#7e22ce,color:#0f172a;",
        "  classDef ext fill:#e2e8f0,stroke:#475569,color:#0f172a;",
    ]
    for lane_id, cls in LANE_CLASS.items():
        ids = [n.id for n in NODES if n.lane == lane_id]
        if ids:
            out.append(f"  class {','.join(ids)} {cls};")
    return "\n".join(out)


# --------------------------------------------------------------------------

def main() -> None:
    here = Path(__file__).parent
    lay = compute_layout()

    bpmn_path = here / "OFC-001.bpmn"
    write_bpmn(bpmn_path, lay)

    mmd_path = here / "OFC-001.mmd"
    mmd_path.write_text(build_mermaid() + "\n", encoding="utf-8")

    px, py, pw, ph = lay["pool"]
    tasks = sum(1 for n in NODES if n.kind == "task")
    gws = sum(1 for n in NODES if n.kind.startswith("gateway"))
    evs = len(NODES) - tasks - gws
    print(f"wrote {bpmn_path.name}: {len(NODES)} flow nodes "
          f"({tasks} tasks, {gws} gateways, {evs} events), "
          f"{len(EDGES)} sequence flows, "
          f"{sum(1 for n in NODES if n.note)} annotations")
    print(f"pool bounds: {pw:.0f} x {ph:.0f} px")
    print(f"wrote {mmd_path.name}")


if __name__ == "__main__":
    main()
