"""IR-driven decomposition and multi-document emission for Phase 3b."""

from __future__ import annotations

from collections import deque
from dataclasses import dataclass, replace
from itertools import product
from pathlib import Path

from bpmn_engine import (
    DecompositionConfig,
    DocumentSpec,
    Edge,
    Node,
    ProcessBundle,
    ProcessModel,
    LayoutError,
    PhaseOrderError,
    Scope,
    Layout,
    compute_layout,
    initial_layout_findings,
    write_bpmn,
)


LAYOUT_REPAIR_PHASE = "phase_layout_repair"


@dataclass(frozen=True)
class PreparedBundle:
    """A decomposed bundle whose every BPMN scope has a computed layout."""

    bundle: ProcessBundle
    layouts: dict[str, dict[str, Layout]]
    repairs: tuple[str, ...] = ()


def _phase_members(model: ProcessModel, phase_id: str,
                   parent_id: str | None) -> list[Node]:
    return [
        node for node in model.nodes
        if node.phase == phase_id and node.parent == parent_id
        and node.kind not in {"subprocess", "call_activity"}
    ]


def _crossing_edges(model: ProcessModel, members: set[str]) -> tuple[list[Edge], list[Edge]]:
    incoming = [edge for edge in model.edges
                if edge.target in members and edge.source not in members]
    outgoing = [edge for edge in model.edges
                if edge.source in members and edge.target not in members]
    return incoming, outgoing


def _next_id(existing: set[str], candidate: str) -> str:
    if candidate not in existing:
        existing.add(candidate)
        return candidate
    index = 2
    while f"{candidate}_{index}" in existing:
        index += 1
    value = f"{candidate}_{index}"
    existing.add(value)
    return value


def _collapse_phase(model: ProcessModel, phase_id: str,
                    parent_id: str | None) -> ProcessModel:
    members = _phase_members(model, phase_id, parent_id)
    if not members:
        return model
    phase_name = dict(model.phases)[phase_id]
    used = {node.id for node in model.nodes}
    prefix = "SubProcess_" + phase_id
    subprocess_id = _next_id(used, prefix)
    child_start_id = _next_id(used, f"{subprocess_id}_Start")
    child_end_id = _next_id(used, f"{subprocess_id}_End")
    owner_lane = members[0].lane
    subprocess = Node(
        id=subprocess_id,
        kind="subprocess",
        lane=owner_lane,
        name=phase_name,
        phase=phase_id,
        parent=parent_id,
        collapsed=True,
    )
    child_start = Node(
        id=child_start_id,
        kind="start_message",
        lane=owner_lane,
        name=f"Start {phase_name}",
        phase=phase_id,
        parent=subprocess_id,
    )
    child_end = Node(
        id=child_end_id,
        kind="end",
        lane=owner_lane,
        name=f"Complete {phase_name}",
        phase=phase_id,
        parent=subprocess_id,
    )
    member_ids = {node.id for node in members}
    incoming, outgoing = _crossing_edges(model, member_ids)

    rewritten: list[Edge] = []
    for edge in model.edges:
        if edge in incoming:
            rewritten.append(replace(edge, target=subprocess_id))
        elif edge in outgoing:
            rewritten.append(replace(edge, source=subprocess_id))
        else:
            rewritten.append(edge)
    rewritten.extend(
        replace(edge, source=child_start_id) for edge in incoming
    )
    rewritten.extend(
        replace(edge, target=child_end_id) for edge in outgoing
    )

    # Collapsing adjacent phases can turn distinct boundary edges into the
    # same parent-level connection.  Preserve branch metadata while removing
    # only exact duplicates; BPMN requires each emitted flow id to be unique.
    unique_edges: list[Edge] = []
    seen_edges: set[tuple[str, str, str, str, bool]] = set()
    for edge in rewritten:
        key = (edge.source, edge.target, edge.label, edge.condition, edge.loop)
        if key in seen_edges:
            continue
        seen_edges.add(key)
        unique_edges.append(edge)

    updated_nodes: list[Node] = []
    inserted = False
    for node in model.nodes:
        if node.id in member_ids:
            if not inserted:
                updated_nodes.append(subprocess)
                inserted = True
            updated_nodes.append(replace(node, parent=subprocess_id))
        else:
            updated_nodes.append(node)
    if not inserted:
        updated_nodes.append(subprocess)
    # Child scope start/end are kept adjacent to their child nodes for stable
    # layout and deterministic XML ordering.
    first_child = next(
        (index for index, node in enumerate(updated_nodes)
         if node.parent == subprocess_id),
        len(updated_nodes),
    )
    updated_nodes[first_child:first_child] = [child_start, child_end]
    return replace(model, nodes=updated_nodes, edges=unique_edges)


def _eligible_phases(model: ProcessModel, parent_id: str | None,
                     config: DecompositionConfig) -> list[str]:
    phases = []
    for phase_id, _ in model.phases:
        members = _phase_members(model, phase_id, parent_id)
        if not members:
            continue
        lanes = {node.lane for node in members}
        if len(lanes) > config.max_lanes_per_collapsed_phase:
            continue
        # A phase with no boundary is not a useful subprocess and is usually
        # an incomplete scope fixture rather than a real decomposition unit.
        incoming, outgoing = _crossing_edges(model, {node.id for node in members})
        if incoming and outgoing:
            phases.append(phase_id)
    return phases


def _needs_split(model: ProcessModel) -> bool:
    scope = Scope.top_level(model)
    layout = compute_layout(model, scope)
    config = model.decomposition
    return (
        len(scope.node_ids) > config.max_nodes_per_plane
        or len(layout.col_center) > config.max_columns
        or (layout.pool is not None and layout.pool[2] > config.max_pool_width)
    )


def decompose_model(model: ProcessModel) -> ProcessModel:
    """Apply the configured, deterministic decomposition policy."""
    config = model.decomposition
    if config.mode == "off":
        return model
    if config.mode != "auto":
        raise ValueError(f"unsupported decomposition mode {config.mode!r}")

    requested = list(config.collapse_phases)
    if requested:
        selected = [phase for phase in requested
                    if phase in _eligible_phases(model, None, config)]
    else:
        selected = []
        if _needs_split(model):
            candidates = _eligible_phases(model, None, config)
            # The phase list is authored order; stable sorting by size first
            # gives deterministic largest-first selection.
            phase_order = {phase_id: index for index, (phase_id, _) in enumerate(model.phases)}
            candidates.sort(key=lambda phase: (-len(_phase_members(model, phase, None)), phase_order[phase]))
            selected = candidates

    result = model
    for phase_id in selected:
        result = _collapse_phase(result, phase_id, None)
        if not requested and not _needs_split(result):
            break
    return result


def scopes_for(model: ProcessModel) -> list[Scope]:
    """Return top-level then nested scopes in deterministic node order."""
    scopes = [Scope.top_level(model)]
    queue = deque(node for node in model.nodes if node.kind == "subprocess")
    while queue:
        subprocess = queue.popleft()
        scopes.append(Scope.child(model, subprocess))
        queue.extend(
            node for node in model.nodes
            if node.kind == "subprocess" and node.parent == subprocess.id
        )
    return scopes


def _normalize_branch_labels(model: ProcessModel) -> tuple[ProcessModel, list[str]]:
    """Supply safe display labels for semantic responses that omitted them."""
    outgoing: dict[str, list[Edge]] = {}
    for edge in model.edges:
        outgoing.setdefault(edge.source, []).append(edge)
    node_by_id = model.by_id()
    changed: list[str] = []
    edges: list[Edge] = []
    for edge in model.edges:
        branches = outgoing[edge.source]
        source = node_by_id[edge.source]
        if source.kind != "gateway_x" or len(branches) < 2 or edge.label.strip():
            edges.append(edge)
            continue
        label = edge.condition or "Otherwise"
        edges.append(replace(edge, label=label))
        changed.append(f"{model.process_id}: labeled {edge.source}->{edge.target} as {label!r}")

    normalized = replace(model, edges=edges)
    for gateway_id, branches in outgoing.items():
        if node_by_id[gateway_id].kind != "gateway_x" or len(branches) < 2:
            continue
        normalized_branches = [edge for edge in normalized.edges if edge.source == gateway_id]
        if any(not edge.label.strip() for edge in normalized_branches):
            raise LayoutError(
                f"exclusive gateway {gateway_id} has an unlabeled branch after presentation normalization"
            )
    return normalized, changed


def _note_lanes(model: ProcessModel) -> tuple[str, ...]:
    lane_ids = {lane_id for lane_id, _ in model.lanes}
    note_lanes: list[str] = []
    for node in model.nodes:
        if node.note is None:
            continue
        if not node.note.strip():
            raise LayoutError(f"node {node.id} has an empty note annotation")
        if node.lane in lane_ids and node.lane not in note_lanes:
            note_lanes.append(node.lane)
    return tuple(note_lanes)


def _annotation_candidates(model: ProcessModel) -> list[ProcessModel]:
    """Return every deterministic above/below arrangement for note lanes."""
    note_lanes = _note_lanes(model)
    base = set(model.ann_above)
    candidates: list[ProcessModel] = []
    for flags in product((False, True), repeat=len(note_lanes)):
        above = base - set(note_lanes)
        above.update(
            lane_id for lane_id, above_lane in zip(note_lanes, flags) if above_lane
        )
        candidates.append(replace(model, ann_above=above))
    return candidates


def _normalize_annotation_placement(
    model: ProcessModel,
) -> tuple[ProcessModel, list[str]]:
    """Choose the cleanest collision-free annotation-band arrangement.

    The raw finding count provides a stable preference among safe candidates;
    ties retain the authored placement whenever possible.  ``compute_layout``
    remains the authoritative final safety check because it also exercises the
    bounded placement repair used by the renderer.
    """
    candidates = _annotation_candidates(model)
    if len(candidates) == 1:
        return model, []

    scored: list[tuple[tuple[int, int, tuple[bool, ...]], ProcessModel]] = []
    failures: list[str] = []
    note_lanes = _note_lanes(model)
    for candidate in candidates:
        try:
            findings = sum(
                len(initial_layout_findings(candidate, scope))
                for scope in scopes_for(candidate)
            )
            for scope in scopes_for(candidate):
                compute_layout(candidate, scope)
        except PhaseOrderError:
            raise
        except LayoutError as exc:
            failures.append(str(exc))
            continue
        score = (
            findings,
            len(candidate.ann_above ^ model.ann_above),
            tuple(lane_id in candidate.ann_above for lane_id in note_lanes),
        )
        scored.append((score, candidate))

    if not scored:
        first_failure = failures[0] if failures else "no viable layout candidate"
        raise LayoutError(
            f"no collision-free annotation-band placement for {model.process_id}; "
            f"tried {len(candidates)} above/below arrangement(s): {first_failure}"
        )
    selected = min(scored, key=lambda item: item[0])[1]
    if selected.ann_above == model.ann_above:
        return selected, []
    placement = ", ".join(
        lane_id for lane_id, _ in model.lanes if lane_id in selected.ann_above
    ) or "none"
    return selected, [
        f"{model.process_id}: selected annotation bands above {placement} "
        "for collision-free layout"
    ]


def normalize_presentation(model: ProcessModel) -> tuple[ProcessModel, list[str]]:
    """Apply build-only presentation repairs before geometry is emitted."""
    labeled, changes = _normalize_branch_labels(model)
    positioned, position_changes = _normalize_annotation_placement(labeled)
    return positioned, changes + position_changes


def _normalize_bundle_presentation(
    bundle: ProcessBundle,
) -> tuple[ProcessBundle, list[str]]:
    models: list[ProcessModel] = []
    repairs: list[str] = []
    for model in bundle.models:
        normalized, changes = normalize_presentation(model)
        models.append(normalized)
        repairs.extend(changes)
    return ProcessBundle(models=models, documents=bundle.documents), repairs


def prepare_bundle(bundle: ProcessBundle) -> ProcessBundle:
    models = [decompose_model(model) for model in bundle.models]
    return ProcessBundle(models=models, documents=bundle.documents)


def _layout_bundle(bundle: ProcessBundle) -> dict[str, dict[str, Layout]]:
    return {
        model.process_id: {
            scope.id: compute_layout(model, scope)
            for scope in scopes_for(model)
        }
        for model in bundle.models
    }


def _repair_phase_layout(model: ProcessModel) -> ProcessModel:
    """Flatten authored phases in a copy for one explicitly repaired build."""

    repair_note = (
        "Build-only layout repair: authored phases were flattened into "
        "phase_layout_repair because their global order conflicted with "
        "the process branching topology. The source IR was not modified."
    )
    process_doc = model.process_doc
    if process_doc:
        process_doc += "\n\n" + repair_note
    else:
        process_doc = repair_note
    return replace(
        model,
        phases=[(LAYOUT_REPAIR_PHASE, "Layout-normalized process")],
        nodes=[replace(node, phase=LAYOUT_REPAIR_PHASE) for node in model.nodes],
        process_doc=process_doc,
        decomposition=replace(
            model.decomposition,
            mode="off",
            collapse_phases=(),
        ),
    )


def prepare_bundle_for_build(
    bundle: ProcessBundle, *, repair_layout: bool = False,
) -> PreparedBundle:
    """Decompose and preflight every scope before any output is created."""

    # Normalize once on the authored process and again after decomposition:
    # each scope has independent geometry, so a safe annotation side can
    # legitimately change when a phase becomes a collapsed subprocess.
    working, repairs = _normalize_bundle_presentation(bundle)
    repaired_processes: set[str] = set()
    while True:
        try:
            prepared = prepare_bundle(working)
            prepared, post_decomposition_repairs = _normalize_bundle_presentation(prepared)
            repairs.extend(post_decomposition_repairs)
            layouts = _layout_bundle(prepared)
            return PreparedBundle(prepared, layouts, tuple(repairs))
        except PhaseOrderError as exc:
            if not repair_layout or exc.process_id in repaired_processes:
                raise
            repaired_processes.add(exc.process_id)
            models = []
            for model in working.models:
                if model.process_id == exc.process_id:
                    models.append(_repair_phase_layout(model))
                else:
                    models.append(model)
            working = ProcessBundle(models=models, documents=working.documents)
            repairs.append(
                f"{exc.process_id}/{exc.scope_id}: flattened authored phases "
                f"after {exc.phase_id} placed {exc.offender_id} before "
                f"{exc.earlier_phase_id} ended"
            )


def write_prepared_bundle(
    directory: Path, prepared: PreparedBundle,
) -> list[Path]:
    """Write a preflighted bundle using its already-computed layouts."""

    bundle = prepared.bundle
    directory.mkdir(parents=True, exist_ok=True)
    specs = list(bundle.documents)
    if not specs:
        specs = [DocumentSpec(bundle.main.process_id, f"{bundle.main.process_id}.bpmn")]
        specs.extend(
            DocumentSpec(model.process_id, f"{model.process_id}.bpmn", "global")
            for model in bundle.models[1:]
        )
    by_id = {model.process_id: model for model in bundle.models}
    paths: list[Path] = []
    for spec in specs:
        model = by_id.get(spec.id)
        if model is None:
            raise ValueError(f"bundle document {spec.id!r} has no process model")
        scopes = scopes_for(model)
        layouts = prepared.layouts[model.process_id]
        path = directory / spec.file
        write_bpmn(path, model, layouts[scopes[0].id], scopes[0], layouts=layouts)
        paths.append(path)
    return paths


def write_bundle(
    directory: Path, bundle: ProcessBundle, *, repair_layout: bool = False,
) -> list[Path]:
    """Preflight and write every process in a bundle."""

    prepared = prepare_bundle_for_build(bundle, repair_layout=repair_layout)
    return write_prepared_bundle(directory, prepared)


__all__ = [
    "decompose_model", "prepare_bundle", "prepare_bundle_for_build",
    "PreparedBundle", "scopes_for", "write_bundle", "write_prepared_bundle",
]
