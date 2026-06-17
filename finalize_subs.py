#!/usr/bin/env python3

from __future__ import annotations

import argparse
import sys
from pathlib import Path

import clean_subs
import rename_subs


def finalize_docx(path: Path) -> Path:
    clean_subs.remove_sources_from_docx(path, path)
    return rename_subs.rename_docx(path)


def parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        prog="finalize-subs",
        description="Run subtitle finalization: clean source markings, then rename to _final.",
    )
    parser.add_argument(
        "paths",
        nargs="*",
        help=(
            "DOCX files to finalize. Default: DOCX files ending in _al or _al_el "
            "in the current directory."
        ),
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Report target filenames without writing changes.",
    )
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv or sys.argv[1:])
    targets = rename_subs.resolve_input_paths(args.paths)
    if not targets:
        print(
            "[warn] no subtitle DOCX files ending in _al or _al_el found",
            file=sys.stderr,
        )
        return 1

    exit_code = 0
    for path in targets:
        if not path.exists():
            print(f"[error] not found: {path}", file=sys.stderr)
            exit_code = 1
            continue
        if not rename_subs.is_rename_candidate(path):
            print(f"[skip] not a finalize candidate: {path}", file=sys.stderr)
            continue

        destination = rename_subs.final_name_for(path)
        if args.dry_run:
            print(f"[target] {path} -> {destination}")
            continue

        try:
            final_path = finalize_docx(path)
        except FileExistsError as exc:
            print(f"[error] {exc}", file=sys.stderr)
            exit_code = 1
            continue

        print(f"[cleaned] {path}")
        print(f"[finalized] {final_path}")

    return exit_code


if __name__ == "__main__":
    raise SystemExit(main())
