#!/usr/bin/env python3
"""Convert transcript BODY sections into SRT files."""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path


DEFAULT_FPS = 30
TIMESTAMP_RE = re.compile(
    r"^(?:XXX\s+)?(?P<start>\d{2}:\d{2}:\d{2}:\d{2})\s+"
    r"(?P<end>\d{2}:\d{2}:\d{2}:\d{2})\s+"
    r"(?P<body>.*\S.*)$"
)


def frame_timecode_to_srt(value: str, fps: int) -> str:
    hh, mm, ss, ff = map(int, value.split(":"))
    total_ms = ((hh * 3600 + mm * 60 + ss) * 1000) + round(ff * 1000 / fps)
    hours = total_ms // 3_600_000
    total_ms %= 3_600_000
    minutes = total_ms // 60_000
    total_ms %= 60_000
    seconds = total_ms // 1_000
    millis = total_ms % 1_000
    return f"{hours:02}:{minutes:02}:{seconds:02},{millis:03}"


def extract_body_lines(text: str) -> list[str]:
    body_started = False
    lines: list[str] = []
    for raw in text.splitlines():
        line = raw.rstrip()
        if not body_started:
            if line.strip() == "BODY:":
                body_started = True
            continue
        if line.strip():
            lines.append(line)
    return lines


def build_srt(text: str, fps: int) -> str:
    lines = extract_body_lines(text)
    cues: list[tuple[str, str, str]] = []
    i = 0
    while i < len(lines):
        match = TIMESTAMP_RE.match(lines[i])
        if not match:
            i += 1
            continue
        start = frame_timecode_to_srt(match.group("start"), fps)
        end = frame_timecode_to_srt(match.group("end"), fps)
        english = lines[i + 1].strip() if i + 1 < len(lines) else ""
        if english.endswith(" #"):
            english = english[:-2].rstrip()
        cues.append((start, end, english))
        i += 1

    out: list[str] = []
    for idx, (start, end, subtitle) in enumerate(cues, 1):
        out.append(str(idx))
        out.append(f"{start} --> {end}")
        out.append(subtitle)
        out.append("")
    return "\n".join(out)


def resolve_input_paths(paths: list[str]) -> list[Path]:
    if paths:
        return [Path(path) for path in paths]
    return sorted(
        path
        for path in Path.cwd().iterdir()
        if path.is_file() and path.suffix == ".txt" and not path.name.endswith(".baseline.txt")
    )


def parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        prog="convert-subs",
        description=(
            "Convert transcript BODY sections into SRT files. "
            "Default: all non-baseline .txt files in the current directory."
        ),
    )
    parser.add_argument(
        "paths",
        nargs="*",
        help="TXT files to convert. Default: all non-baseline .txt files in the current directory.",
    )
    parser.add_argument(
        "--fps",
        type=int,
        default=DEFAULT_FPS,
        help=f"Frame rate used by the source timecodes. Default: {DEFAULT_FPS}",
    )
    return parser.parse_args(argv)


def convert_txt(path: Path, fps: int) -> Path:
    output = path.with_suffix(".srt")
    content = path.read_text(encoding="utf-8", errors="replace")
    srt = build_srt(content, fps)
    output.write_text(srt + "\n", encoding="utf-8")
    return output


def main(argv: list[str] | None = None) -> int:
    args = parse_args(sys.argv[1:] if argv is None else argv)
    targets = resolve_input_paths(args.paths)
    if not targets:
        print("[warn] no non-baseline .txt files found", file=sys.stderr)
        return 1

    exit_code = 0
    for path in targets:
        if not path.exists():
            print(f"[error] not found: {path}", file=sys.stderr)
            exit_code = 1
            continue
        if path.suffix != ".txt":
            print(f"[skip] not a txt file: {path}", file=sys.stderr)
            continue
        if path.name.endswith(".baseline.txt"):
            print(f"[skip] baseline file: {path}", file=sys.stderr)
            continue

        output_path = convert_txt(path, args.fps)
        print(f"[written] {output_path}")

    return exit_code


if __name__ == "__main__":
    raise SystemExit(main())
