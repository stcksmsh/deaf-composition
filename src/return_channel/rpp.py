"""Reader and symbolic extractor for Reaper `.RPP` project files."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

_QUOTES = "\"'`"

NOTE_ON = 0x90
NOTE_OFF = 0x80
EVENT_KEYS = {"E", "e", "Em", "em"}


def tokenize(line: str) -> list[str]:
    """Split an .RPP line into tokens.

    Reaper quotes a value with `"`, falling back to `'` then `` ` `` when the
    value itself contains the preceding quote character.
    """
    tokens: list[str] = []
    i, n = 0, len(line)
    while i < n:
        if line[i].isspace():
            i += 1
            continue
        if line[i] in _QUOTES:
            close = line.index(line[i], i + 1) if line[i] in line[i + 1:] else n
            tokens.append(line[i + 1:close])
            i = close + 1
        else:
            j = i
            while j < n and not line[j].isspace():
                j += 1
            tokens.append(line[i:j])
            i = j
    return tokens


@dataclass
class Block:
    name: str
    args: list[str] = field(default_factory=list)
    entries: list[tuple[str, list[str]]] = field(default_factory=list)
    children: list["Block"] = field(default_factory=list)

    def find(self, name: str) -> "Block | None":
        return next((c for c in self.children if c.name == name), None)

    def find_all(self, name: str) -> list["Block"]:
        return [c for c in self.children if c.name == name]

    def get(self, key: str) -> list[str] | None:
        return next((args for k, args in self.entries if k == key), None)

    def get_all(self, key: str) -> list[list[str]]:
        return [args for k, args in self.entries if k == key]


def parse(text: str) -> Block:
    root = Block("ROOT")
    stack = [root]
    for raw in text.splitlines():
        line = raw.strip()
        if not line:
            continue
        if line == ">":
            if len(stack) > 1:
                stack.pop()
        elif line.startswith("<"):
            tokens = tokenize(line[1:])
            block = Block(tokens[0], tokens[1:])
            stack[-1].children.append(block)
            stack.append(block)
        else:
            tokens = tokenize(line)
            stack[-1].entries.append((tokens[0], tokens[1:]))
    return root


def parse_file(path: str | Path) -> Block:
    """Return the `<REAPER_PROJECT>` block of an .RPP file."""
    root = parse(Path(path).read_text(encoding="utf-8", errors="replace"))
    project = root.find("REAPER_PROJECT")
    if project is None:
        raise ValueError(f"{path}: no <REAPER_PROJECT> block")
    return project


# --- symbolic extraction ---------------------------------------------------


def _floats(args: list[str] | None, count: int) -> list[float]:
    return [float(x) for x in (args or [])[:count]]


def extract_notes(source: Block, ppq: int, sec_per_tick: float, offset_s: float) -> list[dict]:
    """Decode delta-encoded MIDI events from a `<SOURCE MIDI>` block into notes."""
    ticks = 0
    pending: dict[tuple[int, int], tuple[int, int]] = {}
    notes: list[dict] = []
    for key, args in source.entries:
        if key not in EVENT_KEYS or len(args) < 4:
            continue
        ticks += int(args[0])
        status, pitch, vel = int(args[1], 16), int(args[2], 16), int(args[3], 16)
        kind, channel = status & 0xF0, status & 0x0F
        if kind == NOTE_ON and vel > 0:
            pending[(channel, pitch)] = (ticks, vel)
        elif kind == NOTE_OFF or (kind == NOTE_ON and vel == 0):
            start = pending.pop((channel, pitch), None)
            if start is None:
                continue
            start_ticks, velocity = start
            notes.append({
                "pitch": pitch,
                "velocity": velocity,
                "channel": channel,
                "start_ticks": start_ticks,
                "end_ticks": ticks,
                "start_s": offset_s + start_ticks * sec_per_tick,
                "end_s": offset_s + ticks * sec_per_tick,
            })
    notes.sort(key=lambda note: (note["start_ticks"], note["pitch"]))
    return notes


def extract_automation(block: Block) -> list[dict]:
    """Envelope blocks (`PARMENV`, `VOLENV`, ...) with their `PT` points."""
    envelopes = []
    for child in block.children:
        if child.name.endswith("ENV") and child.get("PT") is not None:
            envelopes.append({
                "kind": child.name,
                "name": child.args[-1] if child.args else child.name,
                "points": [
                    {"time": float(pt[0]), "value": float(pt[1]),
                     "shape": int(pt[2]) if len(pt) > 2 else 0}
                    for pt in child.get_all("PT")
                ],
            })
        envelopes.extend(extract_automation(child))
    return envelopes


def _js_params(block: Block) -> list[float | None]:
    """A JS effect's single data line is its parameter vector; `-` means unset."""
    if not block.entries:
        return []
    key, args = block.entries[0]
    params = [None if tok == "-" else float(tok) for tok in [key] + args]
    while params and params[-1] is None:
        params.pop()
    return params


def extract_fx(chain: Block) -> list[dict]:
    """Plugins in an `<FXCHAIN>` / `<MASTERFXLIST>`, with params where readable."""
    fx = []
    for slot, child in enumerate(chain.children):
        if child.name in ("VST", "AU", "CLAP"):
            fx.append({
                "slot": slot,
                "type": child.name,
                "name": child.args[0] if child.args else "",
                "binary": child.args[1] if len(child.args) > 1 else "",
                # VST state is an opaque base64 chunk; params are unreadable by design.
                "params": None,
            })
        elif child.name == "JS":
            fx.append({
                "slot": slot,
                "type": "JS",
                "name": child.args[0] if child.args else "",
                "binary": "",
                "params": _js_params(child),
            })
    return fx


def extract_regions(project: Block) -> list[dict]:
    """`MARKER` lines pair by index: two entries with the same index is a region."""
    by_index: dict[int, list[tuple[float, str]]] = {}
    for args in project.get_all("MARKER"):
        by_index.setdefault(int(args[0]), []).append((float(args[1]), args[2]))
    regions = []
    for index, marks in sorted(by_index.items()):
        marks.sort()
        name = next((n for _, n in marks if n), "")
        if len(marks) > 1:
            regions.append({"index": index, "name": name,
                            "start": marks[0][0], "end": marks[-1][0]})
        else:
            regions.append({"index": index, "name": name,
                            "start": marks[0][0], "end": None})
    return regions


def extract_symbolic(project: Block) -> dict:
    """Everything the return channel can know without listening: plan §8.1."""
    tempo = _floats(project.get("TEMPO"), 3) or [120.0, 4.0, 4.0]
    bpm = tempo[0]
    time_sig = [int(tempo[1]), int(tempo[2])] if len(tempo) == 3 else [4, 4]
    selection = _floats(project.get("SELECTION"), 2)

    tracks, fx, notes, automation = [], [], [], []
    master = project.find("MASTERFXLIST")
    if master is not None:
        fx += [dict(plugin, track="<master>") for plugin in extract_fx(master)]

    folder_depth = 0
    for track_index, track in enumerate(project.find_all("TRACK")):
        name_args = track.get("NAME")
        name = name_args[0] if name_args else ""
        mutesolo = track.get("MUTESOLO") or ["0", "0"]
        isbus = track.get("ISBUS") or ["0", "0"]
        tracks.append({
            "index": track_index,
            "guid": track.args[0] if track.args else "",
            "name": name,
            "is_folder": isbus[0] == "1",
            "folder_depth": folder_depth,
            "channels": int((track.get("NCHAN") or ["2"])[0]),
            "volume": _floats(track.get("VOLPAN"), 2),
            "muted": mutesolo[0] != "0",
            # MAINSEND 0 only disables the *direct* send to master. A track
            # nested in a folder still reaches master through its parent bus,
            # so this alone does not mean the track is inaudible.
            "main_send": (track.get("MAINSEND") or ["1"])[0] != "0",
        })
        folder_depth += int(isbus[1]) if len(isbus) > 1 else 0

        chain = track.find("FXCHAIN")
        if chain is not None:
            fx += [dict(plugin, track=name) for plugin in extract_fx(chain)]
        automation += [dict(env, track=name) for env in extract_automation(track)]

        for item_index, item in enumerate(track.find_all("ITEM")):
            position = float((item.get("POSITION") or ["0"])[0])
            for source in item.find_all("SOURCE"):
                if not source.args or source.args[0] != "MIDI":
                    continue
                hasdata = source.get("HASDATA")
                ppq = int(hasdata[1]) if hasdata and len(hasdata) > 1 else 960
                sec_per_tick = 60.0 / bpm / ppq
                notes += [
                    dict(note, track=name, item=item_index)
                    for note in extract_notes(source, ppq, sec_per_tick, position)
                ]

    return {
        "tempo": bpm,
        "time_sig": time_sig,
        "sample_rate": int((project.get("SAMPLERATE") or ["48000"])[0]),
        "bounds": {
            "selection": {"start": selection[0], "end": selection[1]} if len(selection) == 2 else None,
            "regions": extract_regions(project),
            "render": render_config(project),
        },
        "tracks": tracks,
        "fx": fx,
        "notes": notes,
        "automation": automation,
    }


# --- render configuration --------------------------------------------------

BOUNDS_PROJECT = 1
BOUNDS_REGIONS = 3


def render_config(project: Block) -> dict:
    """`RENDER_RANGE` field 0 is the bounds mode; a `$region` pattern splits output."""
    render_range = project.get("RENDER_RANGE") or []
    pattern = (project.get("RENDER_PATTERN") or [""])[0]
    return {
        "bounds": int(render_range[0]) if render_range else BOUNDS_PROJECT,
        "pattern": pattern,
        "batches_regions": (
            bool(render_range) and int(render_range[0]) == BOUNDS_REGIONS
            and "$region" in pattern
        ),
    }
