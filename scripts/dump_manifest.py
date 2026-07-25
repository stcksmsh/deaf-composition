#!/usr/bin/env python3
"""Run dump_manifest.lua headless and collect manifest.json.

Reaper's own quit command hangs under Xvfb waiting for an unsave-changes
dialog click that never comes (no window manager, no automation) -- so this
polls for the output file instead of trusting the Lua script's own
Main_OnCommand(40004) quit to actually exit, and kills the process once the
file has landed and stopped growing.

RUN
    python scripts/dump_manifest.py -o manifest.json
"""

from __future__ import annotations

import argparse
import os
import signal
import subprocess
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
LUA_SCRIPT = HERE / "dump_manifest.lua"
MARKER_PATH = Path("/tmp/dump_manifest_out_path.txt")
POLL_S = 1.0
SETTLE_S = 2.0     # file must be unchanged for this long before we call it done
TIMEOUT_S = 120


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("-o", "--out", type=Path, default=Path("manifest.json"))
    args = parser.parse_args(argv)

    out_path = args.out.resolve()
    out_path.parent.mkdir(parents=True, exist_ok=True)
    if out_path.exists():
        out_path.unlink()
    MARKER_PATH.write_text(str(out_path) + "\n", encoding="utf-8")

    # xvfb-run is a wrapper script: it forks Xvfb + the real command as
    # children, so killing the xvfb-run PID alone leaves reaper (and, for
    # bridged plugins, wineserver/yabridge-host) running as orphans. Put it
    # in its own process group and kill the whole group on cleanup.
    proc = subprocess.Popen(["xvfb-run", "-a", "reaper", "-nosplash", str(LUA_SCRIPT)],
                            start_new_session=True)

    started = time.monotonic()
    last_size, unchanged_since = -1, None
    try:
        while time.monotonic() - started < TIMEOUT_S:
            time.sleep(POLL_S)
            if out_path.is_file():
                size = out_path.stat().st_size
                if size == last_size and size > 0:
                    if unchanged_since is None:
                        unchanged_since = time.monotonic()
                    elif time.monotonic() - unchanged_since > SETTLE_S:
                        break
                else:
                    unchanged_since = None
                last_size = size
    finally:
        try:
            os.killpg(proc.pid, signal.SIGTERM)
        except ProcessLookupError:
            pass
        try:
            proc.wait(timeout=10)
        except subprocess.TimeoutExpired:
            try:
                os.killpg(proc.pid, signal.SIGKILL)
            except ProcessLookupError:
                pass

    if not out_path.is_file():
        raise SystemExit(f"reaper exited without producing {out_path}")
    print(f"wrote {out_path} ({out_path.stat().st_size} bytes)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
