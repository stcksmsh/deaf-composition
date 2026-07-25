#!/usr/bin/env python3
"""Local web UI for labeling reference-library section boundaries.

Serves references/_raw/*.wav with a waveform view, an audio player, and an
editable segment table (start/end/section_type/name) seeded from whatever
suggest_boundaries.py already generated in references/_boundaries/. Saves
back to the same manifest.json files, or cuts clips directly via cut_clips.

Stdlib only (http.server) -- no new dependency for what's fundamentally a
few endpoints and a page of vanilla JS.

RUN
    python scripts/label_ui.py
    -> open http://localhost:8765
"""

from __future__ import annotations

import json
import sys
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, quote, urlparse

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(HERE.parent / "src"))

from cut_clips import cut_one  # noqa: E402
from suggest_boundaries import _envelopes, FRAME_S  # noqa: E402
from return_channel.reference import SECTION_TYPES, UNLABELED  # noqa: E402

ROOT = HERE.parent
RAW_DIR = ROOT / "references" / "_raw"
BOUNDARIES_DIR = ROOT / "references" / "_boundaries"
REFERENCES_ROOT = ROOT / "references"
PORT = 8765

SECTION_OPTIONS = list(SECTION_TYPES) + [UNLABELED]
_waveform_cache: dict[str, list] = {}


def _tracks() -> list[Path]:
    return sorted(RAW_DIR.glob("*.wav"))


def _manifest_path(name: str) -> Path:
    return BOUNDARIES_DIR / f"{name}.manifest.json"


def _load_manifest(name: str) -> list:
    path = _manifest_path(name)
    if path.is_file():
        return json.loads(path.read_text(encoding="utf-8"))
    return []


def _waveform(name: str) -> list[dict]:
    if name not in _waveform_cache:
        track = RAW_DIR / f"{name}.wav"
        times, level_db, _ = _envelopes(track)
        # Downsample to ~400 points regardless of track length -- the client
        # doesn't need per-frame resolution, just the shape.
        n = len(times)
        target = 400
        stride = max(1, n // target)
        points = [{"t": round(float(times[i]), 2), "db": round(float(level_db[i]), 1)}
                 for i in range(0, n, stride)]
        _waveform_cache[name] = points
    return _waveform_cache[name]


PAGE_TEMPLATE = """<!doctype html>
<html><head><meta charset="utf-8"><title>{title}</title>
<style>
body {{ font-family: system-ui, sans-serif; margin: 2rem; max-width: 1000px; }}
h1 {{ font-size: 1.1rem; }}
a {{ color: #06c; }}
table {{ border-collapse: collapse; width: 100%; margin-top: 1rem; }}
td, th {{ border: 1px solid #ccc; padding: 4px 6px; font-size: 0.9rem; }}
input, select {{ width: 100%; box-sizing: border-box; font-size: 0.9rem; }}
input[type=text] {{ width: 16rem; }}
button {{ margin: 0.2rem; }}
#wave {{ width: 100%; height: 120px; background: #111; display: block; cursor: crosshair; }}
.seekbtn {{ cursor: pointer; }}
#status {{ color: #080; font-weight: bold; }}
</style></head>
<body>
<p><a href="/">&larr; all tracks</a></p>
<h1>{title}</h1>
<audio id="player" controls src="/audio?name={qname}" style="width:100%"></audio>
<svg id="wave" viewBox="0 0 1000 120" preserveAspectRatio="none"></svg>
<p id="status"></p>
<table id="segs"><thead><tr>
  <th>start (s)</th><th>end (s)</th><th>section_type</th><th>name</th><th></th>
</tr></thead><tbody></tbody></table>
<button onclick="addSeg()">+ add segment (at playhead)</button>
<button onclick="save()">Save manifest</button>
<button onclick="cut()">Save + cut clips now</button>

<script>
const NAME = {name_json};
const SOURCE_PATH = {source_json};
const SECTION_OPTIONS = {options_json};
let segs = {segs_json};
let waveform = {waveform_json};
const player = document.getElementById('player');

function drawWave() {{
  const svg = document.getElementById('wave');
  if (!waveform.length) return;
  const duration = waveform[waveform.length - 1].t || 1;
  const dbs = waveform.map(p => p.db).filter(d => isFinite(d));
  const min = Math.min(...dbs), max = Math.max(...dbs);
  const scaleY = d => 120 - ((d - min) / (max - min + 1e-9)) * 110 - 5;
  const pts = waveform.map(p => `${{(p.t / duration * 1000).toFixed(1)}},${{scaleY(p.db).toFixed(1)}}`).join(' ');
  svg.innerHTML = `<polyline points="${{pts}}" fill="none" stroke="#4f8" stroke-width="1"/>`;
  svg.dataset.duration = duration;
  svg.onclick = (e) => {{
    const rect = svg.getBoundingClientRect();
    const frac = (e.clientX - rect.left) / rect.width;
    player.currentTime = frac * duration;
    player.play();
  }};
}}

function render() {{
  const tbody = document.querySelector('#segs tbody');
  tbody.innerHTML = '';
  segs.forEach((s, i) => {{
    const tr = document.createElement('tr');
    tr.innerHTML = `
      <td><input type="number" step="0.1" value="${{s.start}}" onchange="segs[${{i}}].start=parseFloat(this.value)">
          <button class="seekbtn" onclick="player.currentTime=segs[${{i}}].start">&#9654;</button></td>
      <td><input type="number" step="0.1" value="${{s.end}}" onchange="segs[${{i}}].end=parseFloat(this.value)">
          <button class="seekbtn" onclick="player.currentTime=segs[${{i}}].end">&#9654;</button></td>
      <td><select onchange="segs[${{i}}].section_type=this.value">
          ${{SECTION_OPTIONS.map(o => `<option value="${{o}}" ${{o===s.section_type?'selected':''}}>${{o}}</option>`).join('')}}
          </select></td>
      <td><input type="text" value="${{s.name}}" onchange="segs[${{i}}].name=this.value"></td>
      <td><button onclick="segs.splice(${{i}},1);render()">delete</button></td>
    `;
    tbody.appendChild(tr);
  }});
}}

function addSeg() {{
  const t = player.currentTime || 0;
  segs.push({{source: SOURCE_PATH, start: Math.round(t*10)/10,
             end: Math.round((t+20)*10)/10, section_type: 'build',
             name: NAME + '_' + Math.round(t) + 's'}});
  render();
}}

async function save() {{
  const res = await fetch('/save?name=' + encodeURIComponent(NAME), {{
    method: 'POST', body: JSON.stringify(segs)}});
  document.getElementById('status').textContent = res.ok ? 'saved manifest' : 'save failed';
}}

async function cut() {{
  const res = await fetch('/cut?name=' + encodeURIComponent(NAME), {{
    method: 'POST', body: JSON.stringify(segs)}});
  const text = await res.text();
  document.getElementById('status').textContent = res.ok ? text : 'cut failed: ' + text;
}}

drawWave();
render();
</script>
</body></html>
"""

INDEX_TEMPLATE = """<!doctype html>
<html><head><meta charset="utf-8"><title>reference library labeling</title>
<style>body{{font-family:system-ui,sans-serif;margin:2rem;}}
table{{border-collapse:collapse;}} td,th{{border:1px solid #ccc;padding:4px 10px;}}</style>
</head><body>
<h1>reference library labeling</h1>
<table><tr><th>track</th><th>segments in manifest</th></tr>
{rows}
</table>
</body></html>
"""


class Handler(BaseHTTPRequestHandler):
    def log_message(self, fmt, *args):
        pass  # keep stdout clean; errors still raise

    def _send(self, code: int, body: bytes, content_type: str = "text/html; charset=utf-8",
              extra_headers: dict | None = None):
        self.send_response(code)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        for k, v in (extra_headers or {}).items():
            self.send_header(k, v)
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        parsed = urlparse(self.path)
        qs = parse_qs(parsed.query)

        if parsed.path == "/":
            rows = []
            for track in _tracks():
                name = track.stem
                n = len(_load_manifest(name))
                rows.append(f'<tr><td><a href="/track?name={quote(name)}">{name}</a></td>'
                           f'<td>{n}</td></tr>')
            self._send(200, INDEX_TEMPLATE.format(rows="\n".join(rows)).encode())
            return

        if parsed.path == "/track":
            name = qs["name"][0]
            segs = _load_manifest(name)
            html = PAGE_TEMPLATE.format(
                title=name, qname=quote(name),
                name_json=json.dumps(name),
                source_json=json.dumps(str(RAW_DIR / f"{name}.wav")),
                options_json=json.dumps(SECTION_OPTIONS),
                segs_json=json.dumps(segs),
                waveform_json=json.dumps(_waveform(name)),
            )
            self._send(200, html.encode())
            return

        if parsed.path == "/audio":
            name = qs["name"][0]
            path = RAW_DIR / f"{name}.wav"
            self._serve_file_with_range(path)
            return

        self._send(404, b"not found")

    def _serve_file_with_range(self, path: Path):
        if not path.is_file():
            self._send(404, b"not found")
            return
        size = path.stat().st_size
        range_header = self.headers.get("Range")
        if range_header:
            unit, _, rng = range_header.partition("=")
            start_s, _, end_s = rng.partition("-")
            start = int(start_s) if start_s else 0
            end = int(end_s) if end_s else size - 1
            end = min(end, size - 1)
            with path.open("rb") as f:
                f.seek(start)
                chunk = f.read(end - start + 1)
            self._send(206, chunk, "audio/wav", {
                "Content-Range": f"bytes {start}-{end}/{size}",
                "Accept-Ranges": "bytes",
            })
        else:
            self._send(200, path.read_bytes(), "audio/wav", {"Accept-Ranges": "bytes"})

    def do_POST(self):
        parsed = urlparse(self.path)
        qs = parse_qs(parsed.query)
        length = int(self.headers.get("Content-Length", 0))
        body = self.rfile.read(length)
        segs = json.loads(body)
        name = qs["name"][0]

        if parsed.path == "/save":
            _manifest_path(name).parent.mkdir(parents=True, exist_ok=True)
            _manifest_path(name).write_text(json.dumps(segs, indent=2) + "\n", encoding="utf-8")
            self._send(200, b"ok", "text/plain")
            return

        if parsed.path == "/cut":
            _manifest_path(name).parent.mkdir(parents=True, exist_ok=True)
            _manifest_path(name).write_text(json.dumps(segs, indent=2) + "\n", encoding="utf-8")
            lines = []
            for entry in segs:
                try:
                    lines.append(cut_one(entry, REFERENCES_ROOT, dry_run=False))
                except Exception as exc:  # noqa: BLE001 - surface to the browser, don't 500 the whole batch
                    lines.append(f"FAILED {entry.get('name')}: {exc}")
            self._send(200, "\n".join(lines).encode(), "text/plain")
            return

        self._send(404, b"not found")


def main() -> int:
    if not RAW_DIR.is_dir() or not any(RAW_DIR.glob("*.wav")):
        raise SystemExit(f"no tracks found in {RAW_DIR}")
    server = ThreadingHTTPServer(("localhost", PORT), Handler)
    print(f"http://localhost:{PORT}  ({len(_tracks())} tracks)")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
