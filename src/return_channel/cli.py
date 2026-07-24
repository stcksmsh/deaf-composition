"""python -m return_channel <project.RPP> — parse, render, analyze, write state.json."""

from __future__ import annotations

import argparse
from pathlib import Path

from . import render, rpp, state


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="return_channel", description=__doc__)
    parser.add_argument("project", type=Path, help="path to a Reaper .RPP project")
    parser.add_argument("-o", "--out", type=Path, default=Path("state"),
                        help="output directory for state.json files")
    parser.add_argument("--render-dir", type=Path, default=None,
                        help="where rendered wavs go (default: <out>/render)")
    parser.add_argument("--batch", action="store_true",
                        help="render one wav per region in a single Reaper invocation")
    parser.add_argument("--wav", type=Path, default=None,
                        help="skip rendering and analyze this wav instead")
    parser.add_argument("--no-embedding", action="store_true",
                        help="skip CLAP (avoids the ~2GB checkpoint download)")
    parser.add_argument("--checkpoint", default=None, help="CLAP checkpoint path")
    args = parser.parse_args(argv)

    symbolic = rpp.extract_symbolic(rpp.parse_file(args.project))
    regions = {r["name"]: r for r in symbolic["bounds"]["regions"] if r["end"] is not None}

    if args.wav:
        rendered, render_info = {args.wav.stem: args.wav}, None
    else:
        render_dir = args.render_dir or args.out / "render"
        result = render.render(args.project, render_dir, batch=args.batch)
        rendered, render_info = result.wavs, result.summary()
        print(f"rendered {len(rendered)} file(s) to {render_dir} "
              f"in {result.wall_s:.2f}s ({result.per_output_s:.2f}s per output)")

    args.out.mkdir(parents=True, exist_ok=True)
    for stem, wav in sorted(rendered.items()):
        node = state.build(
            args.project, wav, symbolic=symbolic, region=regions.get(stem),
            embedding=not args.no_embedding, checkpoint=args.checkpoint,
            render_info=render_info,
        )
        path = state.write(node, args.out / f"{node['meta']['node_id']}.state.json")
        measured = node["measured"]
        print(f"{path}  lufs={measured['lufs']}  "
              f"centroid={measured['spectral_centroid']['median']:.0f}Hz  "
              f"notes={len(node['symbolic']['notes'])}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
