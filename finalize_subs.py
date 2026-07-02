#!/usr/bin/env python3

from __future__ import annotations

import argparse
from dataclasses import dataclass
import os
import subprocess
import sys
from pathlib import Path

import clean_subs
import rename_subs
import thumbnail_subs


@dataclass(frozen=True)
class FinalizeResult:
    final_path: Path
    thumbnail_path: Path
    analysis_path: Path


def finalize_docx(path: Path) -> FinalizeResult:
    clean_subs.remove_sources_from_docx(path, path)
    thumbnail_path = thumbnail_subs.export_thumbnail_from_docx(path)
    analysis_path = analysis_text_path_for_docx(path)
    final_path = rename_subs.rename_docx(path)
    return FinalizeResult(
        final_path=final_path,
        thumbnail_path=thumbnail_path,
        analysis_path=analysis_path,
    )


def analysis_text_path_for_docx(path: Path) -> Path:
    final_path = rename_subs.final_name_for(path)
    stem = final_path.stem
    if stem.endswith(rename_subs.FINAL_SUFFIX):
        stem = stem[: -len(rename_subs.FINAL_SUFFIX)]
    return final_path.with_name(f"{stem}.txt")


def _default_watch_ts() -> Path:
    return Path(os.environ.get("SUB_WATCH_TS", "~/node/sub/src/cli/watch.ts")).expanduser()


def _watch_workdir(watch_ts: Path) -> Path:
    if (
        watch_ts.name == "watch.ts"
        and watch_ts.parent.name == "cli"
        and watch_ts.parent.parent.name == "src"
    ):
        return watch_ts.parent.parent.parent
    return watch_ts.parent


def run_subtitle_analysis(paths: list[Path]) -> int:
    watch_ts = _default_watch_ts()
    if not watch_ts.exists():
        print(f"[warn] watch.ts not found: {watch_ts}", file=sys.stderr)
        return 1

    exit_code = 0
    for path in paths:
        if not path.exists():
            print(f"[warn] analysis text not found: {path}", file=sys.stderr)
            exit_code = 1
            continue

        print(f"[analysis] {path}")
        result = subprocess.run(
            [
                "npx",
                "tsx",
                str(watch_ts),
                "--once",
                str(path),
                "--type",
                "subs",
            ],
            cwd=_watch_workdir(watch_ts),
        )
        if result.returncode != 0:
            exit_code = result.returncode
    return exit_code


def parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        prog="finalize-subs",
        description="Run subtitle finalization: clean source markings, then rename to _final.",
    )
    parser.add_argument(
        "paths",
        nargs="*",
        help=(
            "DOCX files to finalize. Default: DOCX files ending in _al_el or _al_sy "
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
            "[warn] no subtitle DOCX files ending in _al_el or _al_sy found",
            file=sys.stderr,
        )
        return 1

    exit_code = 0
    analysis_paths: list[Path] = []
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
            result = finalize_docx(path)
        except FileExistsError as exc:
            print(f"[error] {exc}", file=sys.stderr)
            exit_code = 1
            continue

        print(f"[cleaned] {path}")
        print(f"[thumbnail] {result.thumbnail_path}")
        print(f"[renamed] {result.final_path}")
        analysis_paths.append(result.analysis_path)

    if analysis_paths:
        analysis_exit_code = run_subtitle_analysis(analysis_paths)
        if analysis_exit_code != 0:
            exit_code = analysis_exit_code
    return exit_code


if __name__ == "__main__":
    raise SystemExit(main())
