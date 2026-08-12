"""Assemble self-contained BPMN review pages from process data bundles.

The preview consumes process models and emitted document paths, not generator
module globals. Each document gets its own lazily-created navigated viewer so
collapsed subprocesses can use bpmn-js drill-down and breadcrumbs.
"""

from __future__ import annotations

import base64
import json
import logging
import re
from dataclasses import dataclass
from pathlib import Path

from bpmn_engine import ProcessModel, PreviewMetadata
from logging_setup import configure
from ofc001_model import MODEL as OFC001_MODEL
from project_paths import ASSETS_DIR, EXAMPLE_BPMN_DIR, PROJECT_ROOT

configure()
logger = logging.getLogger(__name__)

# ``HERE`` remains the project root for callers that used this public module
# constant before the source files were moved under ``src``.
HERE = PROJECT_ROOT
VENDOR = ASSETS_DIR / "vendor"

_PALETTE = (
    ("#1f5f8b", "#e3eef7"),
    ("#8a4a26", "#f7e9e0"),
    ("#7a6010", "#f7f0da"),
    ("#1c6b4c", "#dff0e8"),
    ("#574a8c", "#eae7f6"),
    ("#126782", "#dceff5"),
    ("#7d3f98", "#f0e4f4"),
    ("#41644a", "#e4f0e5"),
)


@dataclass(frozen=True)
class PreviewDocument:
    """One emitted BPMN document and the model used to annotate its viewer."""

    id: str
    filename: str
    model: ProcessModel
    xml: str | None = None
    path: Path | None = None
    label: str | None = None

    def read_xml(self) -> str:
        if self.xml is not None:
            return self.xml
        if self.path is None:
            raise ValueError(f"preview document {self.id!r} has no XML or path")
        return self.path.read_text(encoding="utf-8")


@dataclass(frozen=True)
class PreviewBundle:
    """The complete input to the generic preview renderer."""

    documents: tuple[PreviewDocument, ...]
    primary_id: str | None = None

    def __post_init__(self) -> None:
        documents = tuple(self.documents)
        if not documents:
            raise ValueError("preview bundle requires at least one document")
        ids = [document.id for document in documents]
        if len(ids) != len(set(ids)):
            raise ValueError("preview document ids must be unique")
        primary_id = self.primary_id or documents[0].id
        if primary_id not in ids:
            raise ValueError(f"unknown primary preview document: {primary_id}")
        object.__setattr__(self, "documents", documents)
        object.__setattr__(self, "primary_id", primary_id)

    @property
    def primary(self) -> PreviewDocument:
        return next(document for document in self.documents
                    if document.id == self.primary_id)


DEFAULT_MODEL = OFC001_MODEL
DEFAULT_BUNDLE = PreviewBundle((
    PreviewDocument(
        id="ofc001",
        filename="OFC-001.bpmn",
        model=DEFAULT_MODEL,
        path=EXAMPLE_BPMN_DIR / "OFC-001.bpmn",
    ),
))


def _slug(text: str, fallback: str) -> str:
    result = re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-")
    return result or fallback


def lane_slugs(process_model: ProcessModel) -> dict[str, str]:
    """Return stable CSS-safe lane keys for one process model."""
    used: set[str] = set()
    result: dict[str, str] = {}
    for index, (lane_id, lane_name) in enumerate(process_model.lanes):
        requested = process_model.lane_classes.get(lane_id, lane_name)
        slug = _slug(requested, f"lane-{index}")
        base = slug
        suffix = 2
        while slug in used:
            slug = f"{base}-{suffix}"
            suffix += 1
        used.add(slug)
        result[lane_id] = slug
    return result


def lane_style_css(process_model: ProcessModel) -> str:
    slugs = lane_slugs(process_model)
    styles = []
    for index, (lane_id, _) in enumerate(process_model.lanes):
        slug = slugs[lane_id]
        stroke, tint = _PALETTE[index % len(_PALETTE)]
        styles.append(
            f".sw-{slug} {{ color:{stroke}; background:{tint}; }}\n"
            f".lane-{slug} > .djs-visual > rect {{ "
            f"fill:{tint} !important; stroke:{stroke} !important; }}"
        )
    return "\n".join(styles)


def phase_summary(process_model: ProcessModel = DEFAULT_MODEL
                  ) -> list[tuple[str, str, list[str]]]:
    """Return (number, title, lane slugs) for populated phases."""
    slugs = lane_slugs(process_model)
    out: list[tuple[str, str, list[str]]] = []
    for phase_id, phase_name in process_model.phases:
        members = [node for node in process_model.nodes
                   if node.phase == phase_id]
        if not members:
            continue
        number, _, title = phase_name.partition(". ")
        if not title:
            number, title = "", phase_name
        lanes: list[str] = []
        for node in members:
            slug = slugs[node.lane]
            if slug not in lanes:
                lanes.append(slug)
        out.append((number, title, lanes))
    return out


def _note_parts(note: str) -> tuple[str, str]:
    match = re.match(r"^\[([^]]+)\]\s*(.*)$", note, re.S)
    if match:
        return match.group(1), match.group(2).strip()
    return "", note.strip()


def esc(text: str) -> str:
    return (text.replace("&", "&amp;").replace("<", "&lt;")
                .replace(">", "&gt;").replace('"', "&quot;"))


def _script_json(value: object) -> str:
    return (json.dumps(value, ensure_ascii=False)
            .replace("<", "\\u003c")
            .replace(">", "\\u003e")
            .replace("&", "\\u0026"))


def _metadata(process_model: ProcessModel) -> PreviewMetadata:
    if process_model.preview is not None:
        return process_model.preview
    return PreviewMetadata(
        title=process_model.process_name,
        heading=process_model.process_name,
        eyebrow="BPMN process",
        lede=process_model.process_doc,
        owner=process_model.participant_name,
        version="",
        issued="",
    )


@dataclass(frozen=True)
class DocumentStats:
    """Diagram-wide element counts shown in the preview's stat row."""

    nodes: int
    tasks: int
    gateways: int
    decisions: int
    flows: int
    lanes: int


def _document_stats(process_model: ProcessModel) -> DocumentStats:
    tasks = sum(1 for node in process_model.nodes if node.kind == "task")
    gateways = sum(1 for node in process_model.nodes
                   if node.kind.startswith("gateway"))
    decisions = sum(1 for node in process_model.nodes
                    if node.kind == "gateway_x" and node.name)
    return DocumentStats(
        nodes=len(process_model.nodes),
        tasks=tasks,
        gateways=gateways,
        decisions=decisions,
        flows=len(process_model.edges),
        lanes=len(process_model.lanes),
    )


def _collect_notes(process_model: ProcessModel) -> list[tuple[str, str, str]]:
    notes = []
    for node in process_model.nodes:
        if node.note:
            key, text = _note_parts(node.note)
            notes.append((key, text, node.name))
    notes.sort(key=lambda item: item[0])
    return notes


def _document_payload(document: PreviewDocument, document_id: str) -> dict[str, object]:
    xml = document.read_xml()
    model_lanes = lane_slugs(document.model)
    lane_of = {node.id: model_lanes[node.lane]
               for node in document.model.nodes if node.kind == "task"}
    download = ("data:application/xml;base64,"
                + base64.b64encode(xml.encode("utf-8")).decode("ascii"))
    return {
        "id": document_id,
        "filename": document.filename,
        "xml": xml,
        "laneOf": lane_of,
        "download": download,
    }


def _document_tab_html(document: PreviewDocument, document_id: str, *, selected: bool) -> str:
    label = document.label or document.model.process_name
    selected_attr = "true" if selected else "false"
    return (
        f'<button type="button" class="document-tab" '
        f'data-document-tab="{esc(document_id)}" '
        f'aria-selected="{selected_attr}">{esc(label)}</button>'
    )


def _document_canvas_html(document: PreviewDocument, document_id: str, *, active: bool) -> str:
    label = document.label or document.model.process_name
    active_class = " active" if active else ""
    return (
        f'<div id="canvas-{esc(document_id)}" '
        f'class="doc-viewer{active_class}" data-document-canvas="'
        f'{esc(document_id)}" role="img" aria-label="BPMN diagram of '
        f'{esc(label)}"></div>'
    )


def _lane_legend_html(process_model: ProcessModel, lane_slug_map: dict[str, str]) -> str:
    return "".join(
        f'<li class="legend-item"><span class="swatch sw-{lane_slug_map[lane_id]}">'
        f'</span>{esc(name)}</li>'
        for lane_id, name in process_model.lanes
    )


def _phase_rows_html(process_model: ProcessModel) -> str:
    return "".join(
        f'<li class="phase"><span class="phase-num">{number or "&mdash;"}</span>'
        f'<span class="phase-title">{esc(title)}</span>'
        f'<span class="phase-lanes">'
        + "".join(f'<i class="dot sw-{slug}" aria-hidden="true"></i>'
                  for slug in lanes)
        + "</span></li>"
        for number, title, lanes in phase_summary(process_model)
    )


def _option_rows_html(process_model: ProcessModel) -> str:
    return "".join(
        f'<tr><th scope="row"><span class="opt-key">{esc(option.key)}</span></th>'
        f'<td><strong>{esc(option.title)}</strong><p>{esc(option.trigger)}</p></td>'
        f'<td><code>{esc(option.gateway)}</code></td>'
        f'<td>{esc(option.effect)}</td></tr>'
        for option in process_model.options
    )


def _note_rows_html(notes: list[tuple[str, str, str]]) -> str:
    return "".join(
        f'<div class="note"><span class="note-key">{esc(key)}</span>'
        f'<div><p class="note-text">{esc(text)}</p>'
        f'<p class="note-anchor">{esc(anchor)}</p></div></div>'
        for key, text, anchor in notes
    )


def build(bundle: PreviewBundle = DEFAULT_BUNDLE) -> str:
    primary = bundle.primary
    process_model = primary.model
    metadata = _metadata(process_model)
    document_ids = [_slug(document.id, "document")
                    for document in bundle.documents]
    if len(document_ids) != len(set(document_ids)):
        raise ValueError("preview document ids must be unique after slugging")
    primary_slug = document_ids[bundle.documents.index(primary)]
    primary_lanes = lane_slugs(process_model)

    documents = []
    document_tabs = []
    document_canvases = []
    for document, document_id in zip(bundle.documents, document_ids):
        documents.append(_document_payload(document, document_id))
        selected = document_id == primary_slug
        document_tabs.append(
            _document_tab_html(document, document_id, selected=selected)
        )
        document_canvases.append(
            _document_canvas_html(document, document_id, active=selected)
        )

    stats = _document_stats(process_model)
    notes = _collect_notes(process_model)

    return TEMPLATE.format(
        page_title=esc(metadata.title),
        heading=esc(metadata.heading),
        eyebrow=esc(metadata.eyebrow),
        lede=esc(metadata.lede),
        owner=esc(metadata.owner),
        version=esc(metadata.version),
        issued=esc(metadata.issued),
        notation=esc(metadata.notation),
        structure_title=esc(metadata.structure_title),
        structure_intro=esc(metadata.structure_intro),
        variation_title=esc(metadata.variation_title),
        variation_intro=esc(metadata.variation_intro),
        constraints_title=esc(metadata.constraints_title),
        constraints_intro=esc(metadata.constraints_intro),
        footer=esc(metadata.footer),
        diagram_css=(VENDOR / "diagram-js.css").read_text(encoding="utf-8"),
        bpmn_css=(VENDOR / "bpmn-js.css").read_text(encoding="utf-8"),
        viewer_js=(VENDOR / "bpmn-navigated-viewer.production.min.js")
            .read_text(encoding="utf-8"),
        documents=_script_json(documents),
        primary_id=_script_json(primary_slug),
        download=documents[0]["download"],
        download_filename=esc(primary.filename),
        switcher_class="" if len(documents) > 1 else " single",
        document_tabs="".join(document_tabs),
        document_canvases="".join(document_canvases),
        lane_styles=lane_style_css(process_model),
        nodes=stats.nodes,
        tasks=stats.tasks,
        gateways=stats.gateways,
        decisions=stats.decisions,
        flows=stats.flows,
        lanes=stats.lanes,
        lane_legend=_lane_legend_html(process_model, primary_lanes),
        phase_rows=_phase_rows_html(process_model),
        option_rows=_option_rows_html(process_model),
        note_rows=_note_rows_html(notes),
    )

TEMPLATE = """<title>{page_title}</title>
<style>
{diagram_css}
{bpmn_css}
</style>
<style>
/* ---- tokens: complete light palette on bare :root ------------------- */
:root {{
  --ground:#eef2f5; --surface:#ffffff; --surface-2:#e4ebf0; --sunken:#f6f8fa;
  --ink:#152029; --ink-2:#4a5b68; --ink-3:#778793;
  --rule:#d2dce3; --rule-strong:#b6c4ce;
  --accent:#0f5a70; --accent-ink:#0b4557; --accent-soft:#d9ebf1;
  --shadow:0 1px 2px rgba(21,32,41,.06), 0 8px 24px rgba(21,32,41,.06);

  --so:#1f5f8b;  --so-tint:#e3eef7;
  --led:#8a4a26; --led-tint:#f7e9e0;
  --con:#7a6010; --con-tint:#f7f0da;
  --un:#1c6b4c;  --un-tint:#dff0e8;
  --mht:#574a8c; --mht-tint:#eae7f6;

  --dg-stroke:#2b3a45; --dg-fill:#ffffff; --dg-text:#152029;
  --dg-canvas:#fbfcfd; --dg-band:#f1f5f8;
}}
@media (prefers-color-scheme: dark) {{
  :root:not([data-theme="light"]) {{
    --ground:#0d151d; --surface:#151f2a; --surface-2:#1d2937; --sunken:#111a23;
    --ink:#e7eef4; --ink-2:#a4b4c2; --ink-3:#78899a;
    --rule:#28374a; --rule-strong:#3a4d63;
    --accent:#54b6cf; --accent-ink:#8ed3e5; --accent-soft:#123945;
    --shadow:0 1px 2px rgba(0,0,0,.4), 0 8px 24px rgba(0,0,0,.35);

    --so:#7cb9e4;  --so-tint:#193448;
    --led:#d9a077; --led-tint:#3a2519;
    --con:#d5b45c; --con-tint:#342a0e;
    --un:#6dc49d;  --un-tint:#123227;
    --mht:#aa9de1; --mht-tint:#262048;

    --dg-stroke:#96a8b8; --dg-fill:#182430; --dg-text:#dde7ef;
    --dg-canvas:#0f1922; --dg-band:#131e28;
  }}
}}
:root[data-theme="dark"] {{
  --ground:#0d151d; --surface:#151f2a; --surface-2:#1d2937; --sunken:#111a23;
  --ink:#e7eef4; --ink-2:#a4b4c2; --ink-3:#78899a;
  --rule:#28374a; --rule-strong:#3a4d63;
  --accent:#54b6cf; --accent-ink:#8ed3e5; --accent-soft:#123945;
  --shadow:0 1px 2px rgba(0,0,0,.4), 0 8px 24px rgba(0,0,0,.35);

  --so:#7cb9e4;  --so-tint:#193448;
  --led:#d9a077; --led-tint:#3a2519;
  --con:#d5b45c; --con-tint:#342a0e;
  --un:#6dc49d;  --un-tint:#123227;
  --mht:#aa9de1; --mht-tint:#262048;

  --dg-stroke:#96a8b8; --dg-fill:#182430; --dg-text:#dde7ef;
  --dg-canvas:#0f1922; --dg-band:#131e28;
}}

/* ---- type + base ---------------------------------------------------- */
:root {{
  --serif: Georgia, "Iowan Old Style", "Source Serif 4", ui-serif, serif;
  --sans: -apple-system, BlinkMacSystemFont, "Segoe UI", system-ui,
          "Helvetica Neue", sans-serif;
  --mono: ui-monospace, "Cascadia Mono", "SF Mono", Consolas, monospace;
}}
* {{ box-sizing: border-box; }}
body {{
  margin:0; background:var(--ground); color:var(--ink);
  font-family:var(--sans); font-size:16px; line-height:1.6;
  -webkit-font-smoothing:antialiased;
}}
.wrap {{ max-width:1500px; margin:0 auto; padding:0 clamp(16px,4vw,48px); }}
.col {{ max-width:68ch; }}
h1,h2,h3 {{ font-family:var(--serif); font-weight:600; text-wrap:balance;
           letter-spacing:-.01em; margin:0; }}
h1 {{ font-size:clamp(2rem,4.4vw,3.1rem); line-height:1.08; }}
h2 {{ font-size:1.55rem; line-height:1.2; }}
h3 {{ font-size:1.05rem; }}
p {{ margin:0; }}
code {{ font-family:var(--mono); font-size:.82em; }}

.eyebrow {{
  font-family:var(--mono); font-size:.74rem; letter-spacing:.14em;
  text-transform:uppercase; color:var(--accent); margin:0 0 14px;
}}

/* ---- masthead ------------------------------------------------------- */
header.mast {{
  border-bottom:1px solid var(--rule); background:var(--surface);
  padding:clamp(36px,6vw,72px) 0 0;
}}
.mast-grid {{ display:flex; flex-wrap:wrap; gap:40px 64px;
              align-items:flex-end; justify-content:space-between; }}
.lede {{ color:var(--ink-2); font-size:1.06rem; margin-top:18px;
         max-width:60ch; }}
.docmeta {{ display:flex; gap:28px; flex-wrap:wrap; font-family:var(--mono);
            font-size:.76rem; color:var(--ink-3); letter-spacing:.04em; }}
.docmeta b {{ display:block; color:var(--ink); font-weight:600;
              font-size:.86rem; margin-top:3px; }}

.stats {{
  display:grid; grid-template-columns:repeat(auto-fit,minmax(112px,1fr));
  gap:1px; background:var(--rule); border-top:1px solid var(--rule);
  margin-top:clamp(32px,5vw,56px);
}}
.stat {{ background:var(--surface); padding:16px 4px 18px; }}
.stat .n {{ font-family:var(--serif); font-size:1.85rem; line-height:1;
            font-variant-numeric:tabular-nums; }}
.stat .l {{ font-family:var(--mono); font-size:.68rem; letter-spacing:.1em;
            text-transform:uppercase; color:var(--ink-3); margin-top:7px; }}

/* ---- diagram -------------------------------------------------------- */
.diagram-section {{ padding:clamp(32px,5vw,56px) 0 0; }}
.bar {{ display:flex; flex-wrap:wrap; gap:16px 24px; align-items:center;
        justify-content:space-between; margin-bottom:16px; }}
.legend {{ display:flex; flex-wrap:wrap; gap:6px 18px; list-style:none;
           margin:0; padding:0; font-size:.83rem; color:var(--ink-2); }}
.legend-item {{ display:flex; align-items:center; gap:7px; }}
.swatch {{ width:13px; height:13px; border-radius:3px; flex:none;
           border:1.5px solid currentColor; }}
/* the legend swatch mirrors how a task looks on the diagram; the phase
   dots are solid so they still read at 8px */
.dot {{ width:8px; height:8px; border-radius:50%; display:inline-block;
        background:currentColor !important; }}
.sw-so  {{ color:var(--so);  background:var(--so-tint); }}
.sw-led {{ color:var(--led); background:var(--led-tint); }}
.sw-con {{ color:var(--con); background:var(--con-tint); }}
.sw-un  {{ color:var(--un);  background:var(--un-tint); }}
.sw-mht {{ color:var(--mht); background:var(--mht-tint); }}

.tools {{ display:flex; gap:8px; }}
button, .dl {{
  font:inherit; font-size:.83rem; font-family:var(--mono);
  letter-spacing:.03em; color:var(--ink); background:var(--surface);
  border:1px solid var(--rule-strong); border-radius:5px;
  padding:7px 13px; cursor:pointer; text-decoration:none;
  display:inline-flex; align-items:center; gap:8px;
}}
button:hover, .dl:hover {{ border-color:var(--accent); color:var(--accent); }}
button:focus-visible, .dl:focus-visible {{
  outline:2px solid var(--accent); outline-offset:2px; }}
.dl {{ background:var(--accent-soft); border-color:transparent;
       color:var(--accent-ink); }}

  .doc-viewer {{
  height:min(76vh,780px); background:var(--dg-canvas);
  border:1px solid var(--rule); border-radius:8px; box-shadow:var(--shadow);
  overflow:hidden;
  /* without this, dragging to pan selects the diagram's label text */
  user-select:none; -webkit-user-select:none;
}}
.hint {{ font-size:.8rem; color:var(--ink-3); margin-top:10px;
         font-family:var(--mono); letter-spacing:.02em; }}

/* bpmn-js theming. It sets fill/stroke as inline styles, so every override
   here has to carry !important to win the cascade. */
.djs-container {{ background:var(--dg-canvas) !important; }}
.djs-visual > rect, .djs-visual > circle, .djs-visual > polygon,
.djs-visual > ellipse {{ stroke:var(--dg-stroke) !important; }}
.djs-visual > rect, .djs-visual > polygon,
.djs-visual > circle {{ fill:var(--dg-fill) !important; }}
.djs-visual > path {{ stroke:var(--dg-stroke) !important; }}
.djs-visual > text, .djs-visual > text > tspan {{
  fill:var(--dg-text) !important; }}
marker path, marker polyline, marker circle {{
  stroke:var(--dg-stroke) !important; fill:var(--dg-stroke) !important; }}
/* the pool and its lane bands read as chrome, not as content */
.djs-element[data-element-id^="Participant_"] > .djs-visual > rect,
.djs-element[data-element-id^="Lane_"] > .djs-visual > rect {{
  fill:var(--dg-band) !important; }}
.lane-so  > .djs-visual > rect {{
  fill:var(--so-tint) !important;  stroke:var(--so) !important; }}
.lane-led > .djs-visual > rect {{
  fill:var(--led-tint) !important; stroke:var(--led) !important; }}
.lane-con > .djs-visual > rect {{
  fill:var(--con-tint) !important; stroke:var(--con) !important; }}
.lane-un  > .djs-visual > rect {{
  fill:var(--un-tint) !important;  stroke:var(--un) !important; }}
.lane-mht > .djs-visual > rect {{
  fill:var(--mht-tint) !important; stroke:var(--mht) !important; }}

/* ---- reference ------------------------------------------------------ */
main {{ padding:clamp(48px,7vw,88px) 0 96px; display:grid;
        gap:clamp(48px,7vw,80px); }}
section > .col > .eyebrow {{ margin-bottom:10px; }}
.sec-intro {{ color:var(--ink-2); margin-top:14px; }}

ol.phases {{ list-style:none; margin:28px 0 0; padding:0;
             border-top:1px solid var(--rule); max-width:900px; }}
.phase {{ display:grid; grid-template-columns:52px 1fr auto; gap:16px;
          align-items:center; padding:13px 4px;
          border-bottom:1px solid var(--rule); }}
.phase-num {{ font-family:var(--mono); font-size:.8rem; color:var(--ink-3);
              font-variant-numeric:tabular-nums; }}
.phase-title {{ font-size:.97rem; }}
.phase-lanes {{ display:flex; gap:5px; }}

.tablewrap {{ overflow-x:auto; margin-top:28px;
              border:1px solid var(--rule); border-radius:8px;
              background:var(--surface); }}
table {{ border-collapse:collapse; width:100%; min-width:760px;
         font-size:.92rem; }}
thead th {{ font-family:var(--mono); font-size:.7rem; letter-spacing:.1em;
            text-transform:uppercase; color:var(--ink-3); text-align:left;
            font-weight:500; padding:13px 18px;
            border-bottom:1px solid var(--rule); background:var(--sunken); }}
tbody th, tbody td {{ padding:16px 18px; vertical-align:top; text-align:left;
                      border-bottom:1px solid var(--rule); }}
tbody tr:last-child th, tbody tr:last-child td {{ border-bottom:0; }}
tbody td p {{ color:var(--ink-2); font-size:.87rem; margin-top:5px; }}
/* element ids read as names, so let the table scroll rather than
   hyphenating them mid-word */
tbody td code {{ color:var(--accent); white-space:nowrap; }}
.opt-key {{ font-family:var(--serif); font-size:1.4rem; color:var(--accent);
            font-weight:600; }}

.notes {{ margin-top:28px; display:grid; gap:1px; background:var(--rule);
          border:1px solid var(--rule); border-radius:8px; overflow:hidden; }}
.note {{ display:grid; grid-template-columns:44px 1fr; gap:16px;
         background:var(--surface); padding:18px 20px; }}
.note-key {{ font-family:var(--mono); font-size:.9rem; color:var(--accent);
             font-weight:600; }}
.note-text {{ font-size:.93rem; }}
.note-anchor {{ font-family:var(--mono); font-size:.72rem; color:var(--ink-3);
                margin-top:8px; letter-spacing:.02em; }}
.note-anchor::before {{ content:"\\2937  "; }}

footer {{ border-top:1px solid var(--rule); background:var(--surface);
          padding:32px 0; font-family:var(--mono); font-size:.76rem;
          color:var(--ink-3); }}

@media (max-width:620px) {{
  .phase {{ grid-template-columns:42px 1fr; }}
  .phase-lanes {{ grid-column:2; }}
}}
@media (prefers-reduced-motion: reduce) {{
  * {{ animation:none !important; transition:none !important; }}
}}
{lane_styles}
</style>

<header class="mast">
  <div class="wrap">
    <div class="mast-grid">
      <div>
        <p class="eyebrow">{eyebrow}</p>
        <h1>{heading}</h1>
        <p class="lede">{lede}</p>
      </div>
      <div class="docmeta">
        <div>Owner<b>{owner}</b></div>
        <div>Version<b>{version}</b></div>
        <div>Issued<b>{issued}</b></div>
        <div>Notation<b>{notation}</b></div>
      </div>
    </div>
    <div class="stats">
      <div class="stat"><div class="n">{nodes}</div>
        <div class="l">Flow nodes</div></div>
      <div class="stat"><div class="n">{tasks}</div>
        <div class="l">Tasks</div></div>
      <div class="stat"><div class="n">{decisions}</div>
        <div class="l">Decisions</div></div>
      <div class="stat"><div class="n">{gateways}</div>
        <div class="l">Gateways</div></div>
      <div class="stat"><div class="n">{flows}</div>
        <div class="l">Sequence flows</div></div>
      <div class="stat"><div class="n">{lanes}</div>
        <div class="l">Lanes</div></div>
    </div>
  </div>
</header>

<div class="diagram-section">
  <div class="wrap">
    <div class="bar">
      <ul class="legend">{lane_legend}</ul>
      <div class="tools">
        <button type="button" id="zoom-out" aria-label="Zoom out">&minus;</button>
        <button type="button" id="zoom-in" aria-label="Zoom in">+</button>
        <button type="button" id="start">Start</button>
        <button type="button" id="overview">Overview</button>
        <a class="dl" id="download" download="{download_filename}"
           href="{download}">Download .bpmn</a>
      </div>
    </div>
    <div class="document-switcher{switcher_class}" role="tablist"
         aria-label="BPMN documents">{document_tabs}</div>
    <div class="viewer-stack">{document_canvases}</div>
    <p class="hint">Drag to pan &middot; scroll or ctrl+scroll to zoom
      &middot; click a collapsed subprocess to drill down; the file opens in
      Camunda Modeler, bpmn.io, or Signavio</p>
  </div>
</div>

<main class="wrap">
  <section>
    <div class="col">
      <p class="eyebrow">Structure</p>
      <h2>{structure_title}</h2>
      <p class="sec-intro">{structure_intro}</p>
    </div>
    <ol class="phases">{phase_rows}</ol>
  </section>

  <section>
    <div class="col">
      <p class="eyebrow">Variation</p>
      <h2>{variation_title}</h2>
      <p class="sec-intro">{variation_intro}</p>
    </div>
    <div class="tablewrap">
      <table>
        <thead><tr><th scope="col">Option</th><th scope="col">Trigger</th>
          <th scope="col">Gateway</th><th scope="col">Branch</th></tr></thead>
        <tbody>{option_rows}</tbody>
      </table>
    </div>
  </section>

  <section>
    <div class="col">
      <p class="eyebrow">Constraints</p>
      <h2>{constraints_title}</h2>
      <p class="sec-intro">{constraints_intro}</p>
    </div>
    <div class="notes">{note_rows}</div>
  </section>
</main>

<footer><div class="wrap">{footer}</div></footer>

<script>{viewer_js}</script>
<script>
(function () {{
  var documents = {documents};
  var viewers = {{}};
  var currentId = {primary_id};
  var download = document.getElementById('download');

  function findDocument(id) {{
    return documents.filter(function (doc) {{ return doc.id === id; }})[0];
  }}

  function toStart(canvas) {{
    var vp = canvas.getSize();
    var box = canvas.viewbox().inner;
    if (!vp.height || !box.height) {{
      canvas.zoom('fit-viewport', 'auto');
      return;
    }}
    var scale = Math.min((vp.height - 24) / box.height, 1.15);
    canvas.viewbox({{
      x: box.x - 20,
      y: box.y - (vp.height / scale - box.height) / 2,
      width: vp.width / scale,
      height: vp.height / scale
    }});
  }}

  function importDocument(id) {{
    if (viewers[id]) {{
      return Promise.resolve(viewers[id]);
    }}

    var doc = findDocument(id);
    var viewer = new BpmnJS({{ container: '#canvas-' + id }});
    viewers[id] = viewer;

    // The vendored BpmnJS is the navigated viewer. Its existing navigation
    // module supplies drill-down buttons and breadcrumbs for child planes.
    return viewer.importXML(doc.xml).then(function () {{
      var canvas = viewer.get('canvas');
      var registry = viewer.get('elementRegistry');

      Object.keys(doc.laneOf).forEach(function (nodeId) {{
        var element = registry.get(nodeId);
        if (element) {{
          canvas.addMarker(element, 'lane-' + doc.laneOf[nodeId]);
        }}
      }});

      canvas.resized();
      if (id === currentId) {{
        toStart(canvas);
      }}
      return viewer;
    }}).catch(function (err) {{
      document.getElementById('canvas-' + id).textContent =
        'The diagram could not be rendered: ' + err.message;
      throw err;
    }});
  }}

  function selectDocument(id) {{
    var doc = findDocument(id);
    currentId = id;

    document.querySelectorAll('[data-document-tab]').forEach(function (tab) {{
      var selected = tab.getAttribute('data-document-tab') === id;
      tab.setAttribute('aria-selected', selected ? 'true' : 'false');
    }});
    document.querySelectorAll('[data-document-canvas]').forEach(
      function (canvas) {{
        canvas.classList.toggle('active',
          canvas.getAttribute('data-document-canvas') === id);
      }}
    );

    download.download = doc.filename;
    download.href = doc.download;

    return importDocument(id).then(function (viewer) {{
      var canvas = viewer.get('canvas');
      canvas.resized();
      toStart(canvas);
    }});
  }}

  document.querySelectorAll('[data-document-tab]').forEach(function (tab) {{
    tab.onclick = function () {{
      selectDocument(tab.getAttribute('data-document-tab'));
    }};
  }});

  document.getElementById('start').onclick = function () {{
    if (viewers[currentId]) toStart(viewers[currentId].get('canvas'));
  }};
  document.getElementById('overview').onclick = function () {{
    if (viewers[currentId]) {{
      viewers[currentId].get('canvas').zoom('fit-viewport', 'auto');
    }}
  }};
  document.getElementById('zoom-in').onclick = function () {{
    if (viewers[currentId]) {{
      var canvas = viewers[currentId].get('canvas');
      canvas.zoom(canvas.zoom() * 1.3);
    }}
  }};
  document.getElementById('zoom-out').onclick = function () {{
    if (viewers[currentId]) {{
      var canvas = viewers[currentId].get('canvas');
      canvas.zoom(canvas.zoom() / 1.3);
    }}
  }};

  selectDocument(currentId);
}})();
</script>
"""


def main() -> None:
    out = HERE / "OFC-001-preview.html"
    html = build()
    out.write_text(html, encoding="utf-8")
    logger.info(f"wrote {out.name}: {len(html) / 1024:.0f} KB")


if __name__ == "__main__":
    main()
