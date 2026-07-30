#!/usr/bin/env python3
"""
Minimal direct client for the reaper_mcp_bridge.lua file-based protocol, for bridge
functions that don't have a corresponding MCP tool (e.g. TrackFX_FormatParamValueNormalized,
added locally in reaper_mcp_bridge.lua alongside the other TrackFX_* cases, but with no
Python-side @mcp.tool() wrapper in the third-party twelvetake-reaper-mcp package).

Writes request_<n>.json / polls response_<n>.json directly in the bridge's data dir,
using request ids from a high, unlikely-to-collide range (9000+) since the MCP server's
own numbering isn't controlled by us.
"""
import itertools
import json
import os
import time
from pathlib import Path

BRIDGE_DIR = Path(os.environ.get(
    "REAPER_BRIDGE_DIR",
    str(Path.home() / ".config/REAPER/Scripts/mcp_bridge_data"),
))

# The bridge's dispatcher scans request_1.json .. request_2000.json (see
# reaper_mcp_bridge.lua's `for i = 1, 2000`), so ids must stay in that range --
# 9000+ (originally used here) is silently never picked up. The vendored
# twelvetake-reaper-mcp server cycles its own request ids through the full
# 1-999 range (confirmed: reaper_mcp_server.py's `request_counter = (request_counter
# % 999) + 1`), so this client must live in a genuinely disjoint band -- 1200-1999 --
# rather than share 800-999 with it, which caused real collisions/timeouts under
# sustained load (apply_surge_preset's ~500+ sequential SetParam calls).
_counter = itertools.cycle(range(1200, 2000))


def call(func, args, timeout=10.0, retries=2):
    """retries=2: this call has hit real, occasional bridge-side timeouts
    across independent sessions (not concurrency -- reproduced fully
    sequential too), most often on TrackFX_FormatParamValueNormalized during
    enum-size probing. A single transient miss shouldn't kill a whole
    section's build; retry the same request id fresh before giving up."""
    last_error = None
    for attempt in range(retries + 1):
        try:
            return _call_once(func, args, timeout)
        except TimeoutError as e:
            last_error = e
    raise last_error


def _call_once(func, args, timeout):
    req_id = next(_counter)
    req_path = BRIDGE_DIR / f"request_{req_id}.json"
    resp_path = BRIDGE_DIR / f"response_{req_id}.json"
    if resp_path.exists():
        resp_path.unlink()
    req_path.write_text(json.dumps({"func": func, "args": args}))

    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if resp_path.exists():
            data = json.loads(resp_path.read_text())
            resp_path.unlink()
            return data
        time.sleep(0.2)
    raise TimeoutError(f"{func}{args}: no response within {timeout}s")
