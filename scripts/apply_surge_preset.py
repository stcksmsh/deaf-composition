#!/usr/bin/env python3
"""
Turn a Surge XT .fxp preset file into a list of (reaper_param_index, normalized_value)
ready for TrackFX_SetParam, using scripts/surge_id_map.json (index -> patch-XML id)
and scripts/surge_param_map.json (index -> ctrltype/native range).

Usage:
    python scripts/apply_surge_preset.py <path-to.fxp>
        -> prints a summary and writes scripts/_surge_apply_plan.json

    from apply_surge_preset import build_apply_plan
    plan = build_apply_plan("/path/to/patch.fxp")
    # plan: list of {index, name, normalized, raw, source}
"""
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))
from surge_normalize import normalize  # noqa: E402

TAG_RE = re.compile(r'<(\w+) type="(\d+)" value="([^"]*)"')

# ct_filtersubtype is the one variable-max ctrltype whose choice count depends on
# the filter TYPE currently selected in that specific slot (not a global constant
# like the others in surge_enum_sizes.json) -- it must be probed live, after that
# slot's type param is set, not resolved offline here.
STATE_DEPENDENT_ENUM_CTRLTYPES = {"ct_filtersubtype"}


def parse_fxp(path):
    """Return {id: (type_code, raw_value)}. type 0 = int, 2 = float; others passed as str."""
    data = Path(path).read_bytes()
    start = data.find(b"<?xml")
    if start < 0:
        raise ValueError(f"{path}: no embedded XML patch found (not a Surge .fxp?)")
    xml = data[start:].decode("utf-8", errors="replace")
    out = {}
    for m in TAG_RE.finditer(xml):
        pid, type_code, raw = m.group(1), m.group(2), m.group(3)
        if type_code == "0":
            val = int(raw)
        else:
            val = float(raw)
        out[pid] = (type_code, val)
    return out


def build_apply_plan(fxp_path):
    id_map = json.loads((ROOT / "scripts/surge_id_map.json").read_text())
    param_map = json.loads((ROOT / "scripts/surge_param_map.json").read_text())
    enum_sizes = json.loads((ROOT / "scripts/surge_enum_sizes.json").read_text())
    patch = parse_fxp(fxp_path)

    plan = []
    needs_live_subtype = []  # ct_filtersubtype only -- state-dependent, resolved at apply time
    skipped_no_id = 0
    skipped_not_in_patch = 0
    skipped_unresolved = 0

    for id_entry, map_entry in zip(id_map, param_map):
        assert id_entry["index"] == map_entry["index"]
        pid = id_entry["id"]
        if pid is None:
            skipped_no_id += 1
            continue
        if pid not in patch:
            skipped_not_in_patch += 1
            continue
        if not map_entry["resolved"]:
            skipped_unresolved += 1
            continue
        _, raw = patch[pid]
        ctrltype = map_entry["ctrltype"]
        if map_entry.get("max") is None:
            if ctrltype in STATE_DEPENDENT_ENUM_CTRLTYPES:
                needs_live_subtype.append({
                    "index": map_entry["index"], "name": map_entry["name"],
                    "id": pid, "raw": raw, "ctrltype": ctrltype,
                })
                continue
            enum_max = enum_sizes[ctrltype]["n"] - 1
            norm = normalize(map_entry, raw, enum_max=enum_max)
        else:
            norm = normalize(map_entry, raw)
        plan.append({
            "index": map_entry["index"],
            "name": map_entry["name"],
            "id": pid,
            "raw": raw,
            "normalized": norm,
        })

    return plan, needs_live_subtype, {
        "total_params": len(id_map),
        "applied": len(plan),
        "needs_live_subtype_query": len(needs_live_subtype),
        "skipped_no_id": skipped_no_id,
        "skipped_not_in_patch": skipped_not_in_patch,
        "skipped_unresolved_ctrltype": skipped_unresolved,
    }


def main():
    if len(sys.argv) != 2:
        print("usage: apply_surge_preset.py <path-to.fxp>", file=sys.stderr)
        return 1
    fxp_path = sys.argv[1]
    plan, needs_live_subtype, stats = build_apply_plan(fxp_path)
    dest = ROOT / "scripts/_surge_apply_plan.json"
    dest.write_text(json.dumps(plan, indent=2))
    subtype_dest = ROOT / "scripts/_surge_apply_plan_subtype_pending.json"
    subtype_dest.write_text(json.dumps(needs_live_subtype, indent=2))
    print(json.dumps(stats, indent=2))
    print(f"wrote {dest} ({len(plan)} param assignments)")
    print(f"wrote {subtype_dest} ({len(needs_live_subtype)} pending live subtype query)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
