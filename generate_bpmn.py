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

from pathlib import Path

from bpmn_engine import (
    E, N, Edge, ExternalPool, MessageFlow, Node, ProcessModel, Scope,
    build_mermaid, compute_layout, write_bpmn,
)

# --------------------------------------------------------------------------
# Process model
# --------------------------------------------------------------------------

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
# Process model data
# --------------------------------------------------------------------------

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

# --------------------------------------------------------------------------
# Shared engine model and entry point
# --------------------------------------------------------------------------

LANE_CLASS = {
    SO: "so", LED: "led", CON: "con", UN: "un", MHT: "mht",
}

MODEL = ProcessModel(
    lanes=LANES,
    phases=PHASES,
    nodes=NODES,
    edges=EDGES,
    process_id=PROCESS_ID,
    participant_name="Oklahoma Forensic Center — Security Intake",
    process_doc=PROCESS_DOC,
    process_name="OFC-001 — Security Intakes Consumer",
    participant_id=MAIN_PARTICIPANT,
    collaboration_id=COLLAB_ID,
    definitions_id="Definitions_OFC001",
    exporter="generate_bpmn.py",
    ann_above=ANN_ABOVE,
    lane_classes=LANE_CLASS,
    mermaid_class_defs=[
        "  classDef so fill:#dbeafe,stroke:#1d4ed8,color:#0f172a;",
        "  classDef led fill:#fee2e2,stroke:#b91c1c,color:#0f172a;",
        "  classDef con fill:#fef3c7,stroke:#b45309,color:#0f172a;",
        "  classDef un fill:#dcfce7,stroke:#15803d,color:#0f172a;",
        "  classDef mht fill:#f3e8ff,stroke:#7e22ce,color:#0f172a;",
        "  classDef ext fill:#e2e8f0,stroke:#475569,color:#0f172a;",
    ],
    external_pools=[ExternalPool(
        id=AC_PARTICIPANT,
        name="Admissions Coordinator",
        anchor="StartEvent_ScheduledAdmission",
        width=320,
        height=60,
        gap_above=110,
        mermaid_id="AC",
    )],
    message_flows=[MessageFlow(
        id=AC_MESSAGE_FLOW,
        source=AC_PARTICIPANT,
        target="StartEvent_ScheduledAdmission",
        name="Scheduled admission email",
        mermaid_name="scheduled admission email",
        label_width=140,
        label_height=27,
        label_dx=6,
        label_dy=22,
    )],
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

    bpmn_path = here / "OFC-001.bpmn"
    write_bpmn(bpmn_path, MODEL, lay, scope)

    mmd_path = here / "OFC-001.mmd"
    mmd_path.write_text(build_mermaid(MODEL, scope) + "\n", encoding="utf-8")

    px, py, pw, ph = lay.pool or (0, 0, 0, 0)
    tasks = sum(1 for n in MODEL.nodes if n.kind == "task")
    gws = sum(1 for n in MODEL.nodes if n.kind.startswith("gateway"))
    evs = len(MODEL.nodes) - tasks - gws
    print(f"wrote {bpmn_path.name}: {len(MODEL.nodes)} flow nodes "
          f"({tasks} tasks, {gws} gateways, {evs} events), "
          f"{len(MODEL.edges)} sequence flows, "
          f"{sum(1 for n in MODEL.nodes if n.note)} annotations")
    print(f"pool bounds: {pw:.0f} x {ph:.0f} px")
    print(f"wrote {mmd_path.name}")


if __name__ == "__main__":
    main()
