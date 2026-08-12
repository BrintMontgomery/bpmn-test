"""Generate the OFC-001 BPMN and Mermaid outputs.

The declarative process data lives in :mod:`ofc001_model` so the generator and
the preview consume exactly the same bundle. The module-level aliases remain
temporarily for callers that used the original generator API.
"""

from __future__ import annotations

from pathlib import Path

from bpmn_engine import (
    E, N, Edge, ExternalPool, MessageFlow, Node, ProcessModel, Scope,
    build_mermaid, compute_layout, write_bpmn,
)
from ofc001_model import (
    AC_MESSAGE_FLOW, AC_PARTICIPANT, ANN_ABOVE, BY_ID, COLLAB_ID, EDGES,
    LANES, LANE_CLASS, MAIN_PARTICIPANT, MODEL, NODES, PHASES, PROCESS_DOC,
    PROCESS_ID, PROCESS_OPTIONS, PREVIEW, SO, LED, CON, UN, MHT,
)


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
