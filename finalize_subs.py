#!/usr/bin/env python3

from __future__ import annotations

import argparse
from dataclasses import dataclass
import os
import subprocess
import sys
import tempfile
from pathlib import Path

from docx import Document

import clean_subs
import rename_subs
import thumbnail_subs


@dataclass(frozen=True)
class FinalizeResult:
    final_path: Path
    thumbnail_path: Path
    analysis_text: str


def finalize_docx(path: Path) -> FinalizeResult:
    clean_subs.remove_sources_from_docx(path, path)
    thumbnail_path = thumbnail_subs.export_thumbnail_from_docx(path)
    analysis_text = extract_subtitle_analysis_text(path)
    final_path = rename_subs.rename_docx(path)
    return FinalizeResult(
        final_path=final_path,
        thumbnail_path=thumbnail_path,
        analysis_text=analysis_text,
    )


def _is_subtitle_label(text: str) -> bool:
    return text.strip() in clean_subs.SUBTITLE_LABELS


def _is_other_section_label(text: str) -> bool:
    stripped = text.strip()
    return stripped in clean_subs.SECTION_LABELS and stripped not in clean_subs.SUBTITLE_LABELS


def extract_subtitle_analysis_text(path: Path) -> str:
    lines: list[str] = []
    in_subtitle_section = False
    for paragraph in Document(path).paragraphs:
        text = paragraph.text.strip()
        if _is_subtitle_label(text):
            in_subtitle_section = True
            continue
        if in_subtitle_section and _is_other_section_label(text):
            break
        if not in_subtitle_section:
            continue
        if text:
            lines.append(text)
    return "\n".join(lines) + ("\n" if lines else "")


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


def run_subtitle_analysis(items: list[tuple[Path, str]]) -> int:
    watch_ts = _default_watch_ts()
    if not watch_ts.exists():
        print(f"[warn] watch.ts not found: {watch_ts}", file=sys.stderr)
        return 1

    exit_code = 0
    for source_path, text in items:
        if not text.strip():
            print(f"[warn] no subtitle text found: {source_path}", file=sys.stderr)
            exit_code = 1
            continue

        print(f"[analysis] {source_path}")
        print()
        with tempfile.NamedTemporaryFile(
            mode="w",
            encoding="utf-8",
            suffix=".txt",
            prefix="finalize-subs-analysis-",
            delete=True,
        ) as analysis_file:
            analysis_file.write(text)
            analysis_file.flush()
            result = subprocess.run(
                [
                    "npx",
                    "tsx",
                    str(watch_ts),
                    "--once",
                    analysis_file.name,
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
    analysis_items: list[tuple[Path, str]] = []
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
        print(f"[exported] {result.thumbnail_path}")
        print(f"[renamed] {result.final_path}")
        analysis_items.append((result.final_path, result.analysis_text))

    if analysis_items:
        analysis_exit_code = run_subtitle_analysis(analysis_items)
        if analysis_exit_code != 0:
            exit_code = analysis_exit_code
    return exit_code


if __name__ == "__main__":
    raise SystemExit(main())
