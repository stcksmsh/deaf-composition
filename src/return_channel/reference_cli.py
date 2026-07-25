"""python -m return_channel.reference_cli build|score — fingerprint reference envelopes."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from . import reference


def _build(args: argparse.Namespace) -> int:
    library = reference.build_library(args.root, embedding=not args.no_embedding,
                                      checkpoint=args.checkpoint)
    for section_type in sorted(library):
        envelope = library[section_type]
        print(f"{section_type}: {envelope['n_tracks']} tracks, "
              f"{envelope['n_tracks_measured']} measured, {envelope['n_windows']} windows")
        for warning in envelope["warnings"]:
            print(f"  [warn] {warning}")
    path = reference.save_library(library, args.out)
    print(f"wrote {path}")
    return 0


def _score(args: argparse.Namespace) -> int:
    library = reference.load_library(args.library)
    state = json.loads(args.state.read_text(encoding="utf-8"))
    result = reference.score_node(state, library, args.section_type)
    print(json.dumps(result, indent=2))
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="return_channel.reference_cli", description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)

    build = sub.add_parser("build", help="ingest a reference-audio folder into a library")
    build.add_argument("root", type=Path, help="see reference.py's module docstring for layout")
    build.add_argument("-o", "--out", type=Path, default=Path("reference_library.json"))
    build.add_argument("--no-embedding", action="store_true")
    build.add_argument("--checkpoint", default=None)
    build.set_defaults(func=_build)

    score = sub.add_parser("score", help="score a state.json against a section-type envelope")
    score.add_argument("--library", type=Path, required=True)
    score.add_argument("--state", type=Path, required=True)
    score.add_argument("--section-type", required=True)
    score.set_defaults(func=_score)

    args = parser.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
