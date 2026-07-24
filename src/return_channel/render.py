"""Headless Reaper rendering, using the invocation validated in exp2b_render-levers.sh."""

from __future__ import annotations

import os
import re
import shutil
import subprocess
import tempfile
from pathlib import Path

from . import rpp

REAPER_BIN = os.environ.get("REAPER_BIN", "reaper")
RENDER_TIMEOUT_S = 600

_RENDER_RANGE = re.compile(r"^(\s*)RENDER_RANGE\s+(\S+)(.*)$")
_RENDER_PATTERN = re.compile(r"^(\s*)RENDER_PATTERN\s.*$")


class RenderFailed(RuntimeError):
    pass


def enable_region_batch_render(text: str, pattern: str = "$region") -> str:
    """Switch a project to one-file-per-region rendering.

    PROJECT_BRIEF.md describes this as a manual, per-project step in Reaper's Render
    dialog. It is not: batch_regions.RPP differs from native_short.RPP only in
    RENDER_RANGE's bounds field (1 = entire project, 3 = project regions) and in
    RENDER_PATTERN, which must contain $region or the regions overwrite each other.
    """
    lines = text.splitlines(keepends=True)
    seen_pattern = False
    for i, line in enumerate(lines):
        if match := _RENDER_RANGE.match(line.rstrip("\n")):
            indent, _, rest = match.groups()
            lines[i] = f"{indent}RENDER_RANGE {rpp.BOUNDS_REGIONS}{rest}\n"
        elif _RENDER_PATTERN.match(line.rstrip("\n")):
            indent = line[: len(line) - len(line.lstrip())]
            lines[i] = f"{indent}RENDER_PATTERN {pattern}\n"
            seen_pattern = True
    if not seen_pattern:
        raise RenderFailed("project has no RENDER_PATTERN line to rewrite")
    return "".join(lines)


def _invoke(project: Path, timeout: int) -> subprocess.CompletedProcess:
    return subprocess.run(
        ["xvfb-run", "-a", REAPER_BIN, "-renderproject", str(project)],
        capture_output=True, text=True, timeout=timeout,
    )


def warm_up(project: Path) -> None:
    """One throwaway render. Wine-bridged projects show a ~16s cold-start spike."""
    with tempfile.TemporaryDirectory(prefix="rc-warmup-") as tmp:
        staged = Path(tmp) / project.name
        shutil.copy(project, staged)
        _invoke(staged, RENDER_TIMEOUT_S)


def render(project: str | Path, out_dir: str | Path, batch: bool = False,
           timeout: int = RENDER_TIMEOUT_S) -> dict[str, Path]:
    """Render a project headless; return {output stem: wav path}.

    Renders a copy so repeated runs never churn Backups/ or stray wavs into the
    fixture directory, and so enabling batch mode cannot mutate the real project.
    With `batch`, one invocation produces one wav per region — the single biggest
    render-cost lever (exp2: O + N*r, with O ~7.9s and r ~0.15s).
    """
    project = Path(project).resolve()
    out_dir = Path(out_dir).resolve()
    out_dir.mkdir(parents=True, exist_ok=True)

    text = project.read_text(encoding="utf-8", errors="replace")
    if batch:
        text = enable_region_batch_render(text)

    staged = out_dir / project.name
    staged.write_text(text, encoding="utf-8")

    before = {p: p.stat().st_mtime for p in out_dir.glob("*.wav")}
    result = _invoke(staged, timeout)
    produced = sorted(
        p for p in out_dir.glob("*.wav")
        if p not in before or p.stat().st_mtime > before[p]
    )

    if not produced:
        raise RenderFailed(
            f"reaper exited {result.returncode} and produced no wav in {out_dir}\n"
            f"stdout: {result.stdout.strip()}\nstderr: {result.stderr.strip()}"
        )
    return {p.stem: p for p in produced}
