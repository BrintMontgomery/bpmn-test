"""Assemble OFC-001-preview.html -- a self-contained review page.

The page embeds the real bpmn-js viewer and the generated .bpmn file, so the
reader sees the actual BPMN diagram (pan, zoom, task-type markers) rather
than a redrawing of it. Everything is inlined: published Artifacts run under
a CSP that blocks every external host.

    py generate_bpmn.py && py build_preview.py
"""

from __future__ import annotations

import base64
import json
from pathlib import Path

import generate_bpmn as model

HERE = Path(__file__).parent
VENDOR = HERE / "vendor"

LANE_SLUG = {
    model.SO: "so",
    model.LED: "led",
    model.CON: "con",
    model.UN: "un",
    model.MHT: "mht",
}

OPTIONS = [
    ("A", "Arrival Without Advance Notice",
     "The Deputy arrives without calling ahead or outside the scheduled "
     "time.",
     "Gateway_UnscheduledArrival",
     "Verify the consumer against the admission email and daily plan, "
     "update the packet, then rejoin at the sally-port admission."),
    ("B", "Changed or Rescheduled Admission",
     "The admission date, arrival time, consumer information, or "
     "destination unit changes before arrival.",
     "Gateway_InfoChanged",
     "Work from the most recent email rather than a packet printed from an "
     "earlier schedule, then rejoin before equipment staging."),
    ("C", "Behavioral or Safety Concern",
     "The Deputy reports combative behavior, transport problems, or "
     "threats, or the consumer presents as agitated.",
     "Gateway_SafetyConcern",
     "Record the report, call the unit early, and hold for a nursing "
     "assessment; a second gateway decides whether precautions change "
     "before the Unit Nurse authorizes continuation."),
    ("D", "Multiple Admissions or Escort Constraints",
     "Security is processing multiple admissions, or the primary Officer "
     "cannot complete the shower or unit escort.",
     "Gateway_EscortConstraints",
     "Coordinate an alternate escort plan with the Unit Nurse and Mental "
     "Health Technician instead of the standard pairing."),
    ("E", "Alternate Shower or Nursing Location",
     "The destination unit directs that the shower or nursing activities "
     "happen in a secure unit location.",
     "Gateway_AltLocation",
     "Escort to the designated location and complete nursing activities "
     "there, bypassing the admissions-area shower entirely."),
]


def phase_summary() -> list[tuple[str, str, list[str]]]:
    """(number, title, lane slugs present) for each phase, in order."""
    out = []
    for phase_id, phase_name in model.PHASES:
        members = [n for n in model.NODES if n.phase == phase_id]
        if not members:
            continue
        num, _, title = phase_name.partition(". ")
        if not title:
            num, title = "", phase_name
        lanes = []
        for n in members:
            slug = LANE_SLUG[n.lane]
            if slug not in lanes:
                lanes.append(slug)
        out.append((num, title, lanes))
    return out


def esc(text: str) -> str:
    return (text.replace("&", "&amp;").replace("<", "&lt;")
                .replace(">", "&gt;").replace('"', "&quot;"))


def build() -> str:
    bpmn_xml = (HERE / "OFC-001.bpmn").read_text(encoding="utf-8")
    viewer_js = (VENDOR / "bpmn-navigated-viewer.production.min.js").read_text(
        encoding="utf-8")
    diagram_css = (VENDOR / "diagram-js.css").read_text(encoding="utf-8")
    bpmn_css = (VENDOR / "bpmn-js.css").read_text(encoding="utf-8")

    lane_of = {n.id: LANE_SLUG[n.lane] for n in model.NODES
               if n.kind == "task"}
    download = ("data:application/xml;base64,"
                + base64.b64encode(bpmn_xml.encode("utf-8")).decode("ascii"))

    tasks = sum(1 for n in model.NODES if n.kind == "task")
    gateways = sum(1 for n in model.NODES if n.kind.startswith("gateway"))
    decisions = sum(1 for n in model.NODES
                    if n.kind == "gateway_x" and n.name)

    notes = [(n.note[1], n.note[4:].strip(), n.name)
             for n in model.NODES if n.note]
    notes.sort(key=lambda t: t[0])

    lane_legend = "".join(
        f'<li class="legend-item"><span class="swatch sw-{LANE_SLUG[lid]}">'
        f'</span>{esc(name)}</li>'
        for lid, name in model.LANES)

    phase_rows = "".join(
        f'<li class="phase"><span class="phase-num">{num or "&mdash;"}</span>'
        f'<span class="phase-title">{esc(title)}</span>'
        f'<span class="phase-lanes">'
        + "".join(f'<i class="dot sw-{s}" aria-hidden="true"></i>'
                  for s in lanes)
        + "</span></li>"
        for num, title, lanes in phase_summary())

    option_rows = "".join(
        f"<tr><th scope=\"row\"><span class=\"opt-key\">{k}</span></th>"
        f"<td><strong>{esc(title)}</strong><p>{esc(trigger)}</p></td>"
        f"<td><code>{esc(gw)}</code></td>"
        f"<td>{esc(effect)}</td></tr>"
        for k, title, trigger, gw, effect in OPTIONS)

    note_rows = "".join(
        f'<div class="note"><span class="note-key">{k}</span>'
        f'<div><p class="note-text">{esc(text)}</p>'
        f'<p class="note-anchor">{esc(anchor)}</p></div></div>'
        for k, text, anchor in notes)

    return TEMPLATE.format(
        diagram_css=diagram_css,
        bpmn_css=bpmn_css,
        viewer_js=viewer_js,
        bpmn_xml=json.dumps(bpmn_xml),
        lane_of=json.dumps(lane_of),
        download=download,
        nodes=len(model.NODES),
        tasks=tasks,
        gateways=gateways,
        decisions=decisions,
        flows=len(model.EDGES),
        lanes=len(model.LANES),
        lane_legend=lane_legend,
        phase_rows=phase_rows,
        option_rows=option_rows,
        note_rows=note_rows,
    )


TEMPLATE = """<title>OFC-001 Security Intake</title>
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

#canvas {{
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
</style>

<header class="mast">
  <div class="wrap">
    <div class="mast-grid">
      <div>
        <p class="eyebrow">Operating Checklist &middot; OFC-001</p>
        <h1>Security Intakes Consumer</h1>
        <p class="lede">The controlled process for receiving a consumer from
          law enforcement at the Oklahoma Forensic Center &mdash; transfer of
          custody, security search, electronic tracking and identification,
          and the handoff to nursing staff.</p>
      </div>
      <div class="docmeta">
        <div>Owner<b>OFC Security Unit</b></div>
        <div>Version<b>1.1</b></div>
        <div>Issued<b>2026-08-11</b></div>
        <div>Notation<b>BPMN 2.0</b></div>
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
        <a class="dl" id="download" download="OFC-001.bpmn"
           href="{download}">Download .bpmn</a>
      </div>
    </div>
    <div id="canvas" role="img"
         aria-label="BPMN 2.0 collaboration diagram of the OFC-001 security
         intake process"></div>
    <p class="hint">Drag to pan &middot; scroll or ctrl+scroll to zoom
      &middot; the file opens in Camunda Modeler, bpmn.io, or Signavio</p>
  </div>
</div>

<main class="wrap">
  <section>
    <div class="col">
      <p class="eyebrow">Structure</p>
      <h2>Eleven phases, five lanes</h2>
      <p class="sec-intro">The process runs left to right in a single pool.
        Admissions Coordinator sits outside it as a collapsed participant,
        sending the scheduled admission email that starts the process. Dots
        mark which actors appear in each phase.</p>
    </div>
    <ol class="phases">{phase_rows}</ol>
  </section>

  <section>
    <div class="col">
      <p class="eyebrow">Variation</p>
      <h2>The five options are gateways, not footnotes</h2>
      <p class="sec-intro">Options A&ndash;E in the checklist describe
        departures from the main path. Each one is modeled where it actually
        occurs, as a labeled exclusive gateway with a condition on the
        non-default branch.</p>
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
      <h2>Notes carried onto the diagram</h2>
      <p class="sec-intro">Each note from the checklist is attached to the
        task it governs as a BPMN text annotation, so the constraint travels
        with the model rather than living in a separate document.</p>
    </div>
    <div class="notes">{note_rows}</div>
  </section>
</main>

<footer><div class="wrap">Oklahoma Forensic Center &middot; Security Unit
  &middot; OFC-001 v1.1 &middot; generated from the operating checklist by
  generate_bpmn.py</div></footer>

<script>{viewer_js}</script>
<script>
(function () {{
  var xml = {bpmn_xml};
  var laneOf = {lane_of};
  var viewer = new BpmnJS({{ container: '#canvas' }});

  viewer.importXML(xml).then(function () {{
    var canvas = viewer.get('canvas');
    var registry = viewer.get('elementRegistry');

    Object.keys(laneOf).forEach(function (id) {{
      var el = registry.get(id);
      if (el) canvas.addMarker(el, 'lane-' + laneOf[id]);
    }});

    // The pool is ~8x wider than it is tall. Fitting the whole thing into
    // the frame shrinks it past legibility, so the default view fits the
    // lanes vertically and parks at the start of the process; the reader
    // pans right through it.
    function toStart() {{
      var vp = canvas.getSize();
      var box = canvas.viewbox().inner;
      var scale = Math.min((vp.height - 24) / box.height, 1.15);
      canvas.viewbox({{
        x: box.x - 20,
        y: box.y - (vp.height / scale - box.height) / 2,
        width: vp.width / scale,
        height: vp.height / scale
      }});
    }}

    toStart();
    document.getElementById('start').onclick = toStart;
    document.getElementById('overview').onclick = function () {{
      canvas.zoom('fit-viewport', 'auto');
    }};
    document.getElementById('zoom-in').onclick = function () {{
      canvas.zoom(canvas.zoom() * 1.3);
    }};
    document.getElementById('zoom-out').onclick = function () {{
      canvas.zoom(canvas.zoom() / 1.3);
    }};
  }}).catch(function (err) {{
    document.getElementById('canvas').textContent =
      'The diagram could not be rendered: ' + err.message;
  }});
}})();
</script>
"""


def main() -> None:
    out = HERE / "OFC-001-preview.html"
    html = build()
    out.write_text(html, encoding="utf-8")
    print(f"wrote {out.name}: {len(html) / 1024:.0f} KB")


if __name__ == "__main__":
    main()
