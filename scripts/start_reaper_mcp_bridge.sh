#!/usr/bin/env bash
# Launch the TwelveTake-Studios/reaper-mcp Lua bridge headless and confirm it's live.
#
# Deploys reaper_mcp_bridge.lua to REAPER's Scripts folder (vendored copy at
# scripts/reaper_mcp_bridge.lua -- see fetch step below if it needs updating),
# launches REAPER headless with it as the startup script, and round-trips a
# GetAppVersion request through the file-based bridge protocol to confirm the
# whole chain actually works before handing back control.
#
# Gotchas discovered getting this running (see memory.md for the full story):
#   - reaper.ShowConsoleMsg only writes to REAPER's GUI console, invisible
#     under Xvfb -- you cannot use it to confirm startup. Poll for the bridge
#     directory / a round-trip response instead.
#   - The bridge directory can take 10-20s to appear (REAPER's headless
#     audio/plugin-scan startup, same cold-start cost noted in PROJECT_BRIEF.md
#     §2) -- don't assume a fast failure means it's broken.
#   - xvfb-run is a wrapper script; it forks Xvfb + reaper as children, so
#     killing its own PID orphans a live REAPER process. Use process-group
#     kill (this script's stop mode does).
#
# RUN
#   scripts/start_reaper_mcp_bridge.sh start
#   scripts/start_reaper_mcp_bridge.sh stop

set -euo pipefail

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
BRIDGE_SRC="$HERE/reaper_mcp_bridge.lua"
BRIDGE_DST="$HOME/.config/REAPER/Scripts/reaper_mcp_bridge.lua"
BRIDGE_DATA_DIR="$HOME/.config/REAPER/Scripts/mcp_bridge_data"
PIDFILE="/tmp/reaper_mcp_bridge.pid"
LOGFILE="/tmp/reaper_mcp_bridge.log"

start() {
  if [[ -f "$PIDFILE" ]] && kill -0 "$(cat "$PIDFILE")" 2>/dev/null; then
    echo "already running (pid $(cat "$PIDFILE"))"
    exit 0
  fi

  mkdir -p "$(dirname "$BRIDGE_DST")"
  cp "$BRIDGE_SRC" "$BRIDGE_DST"
  rm -rf "$BRIDGE_DATA_DIR"

  setsid nohup xvfb-run -a reaper -nosplash "$BRIDGE_DST" > "$LOGFILE" 2>&1 &
  echo $! > "$PIDFILE"
  echo "launched (process group $(cat "$PIDFILE")), waiting for bridge to come up..."

  for _ in $(seq 1 30); do
    if [[ -d "$BRIDGE_DATA_DIR" ]]; then
      break
    fi
    sleep 2
  done
  if [[ ! -d "$BRIDGE_DATA_DIR" ]]; then
    echo "bridge directory never appeared -- check $LOGFILE" >&2
    exit 1
  fi

  # Round-trip a real request through the protocol, not just check the directory exists.
  rm -f "$BRIDGE_DATA_DIR"/request_1.json "$BRIDGE_DATA_DIR"/response_1.json
  echo '{"func": "GetAppVersion", "args": []}' > "$BRIDGE_DATA_DIR/request_1.json"
  for _ in $(seq 1 10); do
    if [[ -f "$BRIDGE_DATA_DIR/response_1.json" ]]; then
      echo "bridge live: $(cat "$BRIDGE_DATA_DIR/response_1.json")"
      rm -f "$BRIDGE_DATA_DIR/response_1.json"
      exit 0
    fi
    sleep 1
  done
  echo "bridge directory exists but did not answer a request -- check $LOGFILE" >&2
  exit 1
}

stop() {
  if [[ -f "$PIDFILE" ]]; then
    pgid="$(cat "$PIDFILE")"
    kill -TERM -"$pgid" 2>/dev/null || true
    sleep 1
    kill -KILL -"$pgid" 2>/dev/null || true
    rm -f "$PIDFILE"
  fi
  # Belt and suspenders: xvfb-run's children can outlive the group leader.
  pkill -9 -f "reaper -nosplash.*reaper_mcp_bridge.lua" 2>/dev/null || true
  echo "stopped"
}

case "${1:-}" in
  start) start ;;
  stop) stop ;;
  *) echo "usage: $0 start|stop" >&2; exit 1 ;;
esac
