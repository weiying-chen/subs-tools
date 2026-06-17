#!/usr/bin/env python3

from __future__ import annotations

import argparse
import sys
from pathlib import Path


RENAME_SUFFIXES = ("_al_el", "_al")
FINAL_SUFFIX = "_final"


def final_name_for(path: Path) -> Path:
    stem = path.stem
    for suffix in RENAME_SUFFIXES:
        if stem.endswith(suffix):
            base = stem[: -len(suffix)]
            return path.with_name(f"{base}{FINAL_SUFFIX}{path.suffix}")
    if stem.endswith(FINAL_SUFFIX):
        return path
    raise ValueError(f"unsupported subtitle filename: {path.name}")


def is_rename_candidate(path: Path) -> bool:
    if path.suffix.lower() != ".docx" or path.name.startswith("~$"):
        return False
    return any(path.stem.endswith(suffix) for suffix in RENAME_SUFFIXES)


def resolve_input_paths(raw_paths: list[str]) -> list[Path]:
    if raw_paths:
        return [Path(raw_path) for raw_path in raw_paths]
    return sorted(
        (path for path in Path.cwd().iterdir() if is_rename_candidate(path)),
        key=lambda path: path.name.lower(),
    )


def rename_docx(path: Path) -> Path:
    destination = final_name_for(path)
    if destination == path:
        return path
    if destination.exists():
        raise FileExistsError(f"destination already exists: {destination}")
    return path.replace(destination)


def parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        prog="rename-subs",
        description="Rename generated subtitle DOCX files from _al/_al_el to _final.",
    )
    parser.add_argument(
        "paths",
        nargs="*",
        help=(
            "DOCX files to rename. Default: DOCX files ending in _al or _al_el "
            "in the current directory."
        ),
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Report target filenames without renaming.",
    )
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv or sys.argv[1:])
    targets = resolve_input_paths(args.paths)
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
        if not is_rename_candidate(path):
            print(f"[skip] not a rename candidate: {path}", file=sys.stderr)
            continue

        destination = final_name_for(path)
        if args.dry_run:
            print(f"[target] {path} -> {destination}")
            continue

        try:
            renamed = rename_docx(path)
        except FileExistsError as exc:
            print(f"[error] {exc}", file=sys.stderr)
            exit_code = 1
            continue
        print(f"[renamed] {path} -> {renamed}")

    return exit_code


if __name__ == "__main__":
    raise SystemExit(main())
