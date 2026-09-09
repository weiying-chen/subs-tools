#!/usr/bin/env python3
from __future__ import annotations

import argparse
import re
import sys
import xml.etree.ElementTree as ET
from dataclasses import dataclass
from pathlib import Path
from zipfile import ZipFile

try:
    from rapidfuzz import fuzz
except ImportError:  # pragma: no cover
    fuzz = None


SRT_TIME_RE = re.compile(
    r"^(\d{2}):(\d{2}):(\d{2}),(\d{3})\s+-->\s+"
    r"(\d{2}):(\d{2}):(\d{2}),(\d{3})"
)


@dataclass(frozen=True)
class Cue:
    start: float
    end: float
    text: str


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Convert SubOCR SRT output to timed baseline TXT. "
            "OCR cues remain the authority for timestamps and row grouping."
        )
    )
    parser.add_argument("--srt", required=True, type=Path, help="SubOCR .srt output")
    parser.add_argument(
        "--offset",
        required=True,
        help="Absolute start offset for the clip, e.g. 00:07:51 or 471",
    )
    parser.add_argument(
        "--source",
        type=Path,
        help="Optional clean Chinese source text, .txt or .docx",
    )
    parser.add_argument(
        "--start-marker",
        help="For DOCX/TXT source, first marker before the desired block",
    )
    parser.add_argument(
        "--end-marker",
        help="For DOCX/TXT source, marker after the desired block",
    )
    parser.add_argument(
        "--end-text",
        help="Stop source text at this exact line, inclusive",
    )
    parser.add_argument(
        "--out-baseline",
        required=True,
        type=Path,
        help="Path to write .baseline.txt",
    )
    parser.add_argument(
        "--out-txt",
        type=Path,
        help="Path to write .txt. Defaults to out-baseline without .baseline",
    )
    parser.add_argument(
        "--notes",
        type=Path,
        help="Optional alignment notes path",
    )
    parser.add_argument(
        "--corrections",
        type=Path,
        help=(
            "Optional UTF-8 TSV corrections. Use either start<TAB>text or "
            "start<TAB>end<TAB>text. Corrections are applied after alignment "
            "and never change timestamps or row count."
        ),
    )
    parser.add_argument(
        "--blank-lines-from",
        type=Path,
        help=(
            "Optional existing timed TXT file whose blank-line positions should "
            "be copied. The timestamped rows remain generated from the OCR SRT."
        ),
    )
    parser.add_argument(
        "--max-source-lines-per-cue",
        type=int,
        default=4,
        help="Maximum clean source lines allowed inside one OCR cue",
    )
    parser.add_argument(
        "--min-note-score",
        type=float,
        default=55.0,
        help="Write a note for aligned cues below this fuzzy score",
    )
    parser.add_argument(
        "--taiwan-variants",
        action="store_true",
        help="Normalize common Taiwan Traditional variants, e.g. 台 -> 臺",
    )
    parser.add_argument(
        "--ocr-text",
        action="store_true",
        help="Ignore clean source text and write cleaned OCR text only",
    )
    return parser.parse_args()


def parse_offset(value: str) -> float:
    if re.fullmatch(r"\d+(\.\d+)?", value):
        return float(value)
    parts = value.split(":")
    if len(parts) != 3:
        raise ValueError(f"invalid offset: {value}")
    hours, minutes, seconds = parts
    return int(hours) * 3600 + int(minutes) * 60 + float(seconds)


def parse_srt_time(groups: tuple[str, ...], start: int) -> float:
    hours, minutes, seconds, milliseconds = (int(v) for v in groups[start : start + 4])
    return hours * 3600 + minutes * 60 + seconds + milliseconds / 1000


def parse_srt(path: Path) -> list[Cue]:
    content = path.read_text(encoding="utf-8-sig").replace("\r\n", "\n").replace("\r", "\n")
    blocks = [block.strip() for block in re.split(r"\n\s*\n", content) if block.strip()]
    cues: list[Cue] = []
    for block in blocks:
        lines = block.splitlines()
        time_index = next((i for i, line in enumerate(lines) if "-->" in line), None)
        if time_index is None:
            continue
        match = SRT_TIME_RE.match(lines[time_index].strip())
        if not match:
            continue
        text = "".join(line.strip() for line in lines[time_index + 1 :] if line.strip())
        cues.append(
            Cue(
                start=parse_srt_time(match.groups(), 0),
                end=parse_srt_time(match.groups(), 4),
                text=text,
            )
        )
    if not cues:
        raise ValueError(f"no SRT cues found in {path}")
    return cues


def read_docx_lines(path: Path) -> list[str]:
    ns = {"w": "http://schemas.openxmlformats.org/wordprocessingml/2006/main"}
    with ZipFile(path) as archive:
        xml = archive.read("word/document.xml")
    root = ET.fromstring(xml)
    lines: list[str] = []
    for para in root.findall(".//w:p", ns):
        text = "".join((node.text or "") for node in para.findall(".//w:t", ns)).strip()
        if text:
            lines.append(text)
    return lines


def read_source_lines(path: Path) -> list[str]:
    if path.suffix.lower() == ".docx":
        return read_docx_lines(path)
    return [
        line.strip()
        for line in path.read_text(encoding="utf-8-sig").replace("\r\n", "\n").splitlines()
        if line.strip()
    ]


def slice_source(
    lines: list[str],
    *,
    start_marker: str | None,
    end_marker: str | None,
    end_text: str | None,
) -> list[str]:
    start = 0
    end = len(lines)
    if start_marker:
        start = lines.index(start_marker) + 1
    if end_marker:
        end = lines.index(end_marker, start)
    selected = [line for line in lines[start:end] if line.strip()]
    if end_text:
        selected = selected[: selected.index(end_text) + 1]
    return selected


def normalize_for_match(text: str) -> str:
    text = (
        text.replace("臺", "台")
        .replace("舞臺", "舞台")
        .replace("關註", "關注")
        .replace("富歸", "賦歸")
        .replace("二二八", "228")
    )
    return re.sub(r"[\s，。！？、,.!?：:；;（）()#\-]", "", text)


def clean_text(text: str, *, taiwan_variants: bool) -> str:
    replacements = {
        "KSPIRIT": "",
        "SPIRIT": "",
        "PIRIT": "",
        "關註": "關注",
        "富歸": "賦歸",
        "二二八": "228",
    }
    for old, new in replacements.items():
        text = text.replace(old, new)
    if taiwan_variants:
        text = text.replace("台", "臺")
    return text.strip()


def read_corrections(path: Path | None) -> dict[str, str]:
    if path is None:
        return {}
    corrections: dict[str, str] = {}
    for line_number, line in enumerate(path.read_text(encoding="utf-8-sig").splitlines(), start=1):
        if not line.strip() or line.lstrip().startswith("#"):
            continue
        parts = line.split("\t")
        if len(parts) == 2:
            start, text = parts
        elif len(parts) >= 3:
            start, _end, text = parts[0], parts[1], "\t".join(parts[2:])
        else:
            raise ValueError(f"{path}:{line_number}: expected start<TAB>text")
        corrections[start.strip()] = text.strip()
    return corrections


def read_blank_lines(path: Path | None) -> set[str]:
    if path is None:
        return set()
    blank_before: set[str] = set()
    prefix_lines = read_layout_prefixes(path)
    for timestamp, lines in prefix_lines.items():
        if any(not line for line in lines):
            blank_before.add(timestamp)
    return blank_before


def is_timed_row(line: str) -> bool:
    return bool(re.match(r"^\d{2}:\d{2}:\d{2}:\d{2}\t", line))


def read_layout_prefixes(path: Path | None) -> dict[str, list[str]]:
    if path is None:
        return {}
    prefixes: dict[str, list[str]] = {}
    pending: list[str] = []
    for line in path.read_text(encoding="utf-8-sig").splitlines():
        if not is_timed_row(line):
            pending.append(line)
            continue
        timestamp = line.split("\t", 1)[0].strip()
        if pending:
            prefixes[timestamp] = pending
            pending = []
    return prefixes


def align_source_to_cues(
    cues: list[Cue],
    source_lines: list[str],
    *,
    max_source_lines_per_cue: int,
) -> tuple[list[str], list[tuple[int, float, int, int]]]:
    if fuzz is None:
        raise RuntimeError("rapidfuzz is required when --source is used")

    n = len(cues)
    m = len(source_lines)
    inf = 10**9
    dp = [[inf] * (m + 1) for _ in range(n + 1)]
    back: list[list[tuple[int, int, float] | None]] = [[None] * (m + 1) for _ in range(n + 1)]
    dp[0][0] = 0.0

    for i, cue in enumerate(cues):
        ocr_text = normalize_for_match(cue.text)
        for j in range(m + 1):
            if dp[i][j] >= inf:
                continue
            for size in range(1, max_source_lines_per_cue + 1):
                if j + size > m:
                    break
                source_text = "".join(source_lines[j : j + size])
                score = fuzz.ratio(ocr_text, normalize_for_match(source_text))
                length_penalty = abs(len(normalize_for_match(source_text)) - len(ocr_text)) * 0.15
                split_penalty = (size - 1) * 1.5
                cost = (100 - score) + length_penalty + split_penalty
                value = dp[i][j] + cost
                if value < dp[i + 1][j + size]:
                    dp[i + 1][j + size] = value
                    back[i + 1][j + size] = (j, size, score)

    # Prefer consuming the full supplied/highlighted source. If the source is
    # shorter than OCR, stop at the best prefix and drop unmatched OCR tail.
    best_i = n
    best_j = m
    if back[n][m] is None:
        candidates = [(i, dp[i][m]) for i in range(1, n + 1) if back[i][m] is not None]
        if not candidates:
            raise RuntimeError("could not align source text to OCR cues")
        best_i, _ = min(candidates, key=lambda item: item[1])

    items: list[tuple[int, int, int, float]] = []
    i, j = best_i, best_j
    while i > 0:
        previous = back[i][j]
        if previous is None:
            raise RuntimeError(f"alignment failed at cue {i}, source line {j}")
        source_start, size, score = previous
        items.append((i - 1, source_start, size, score))
        i -= 1
        j = source_start
    items.reverse()

    texts: list[str] = []
    notes: list[tuple[int, float, int, int]] = []
    for cue_index, source_start, size, score in items:
        texts.append("".join(source_lines[source_start : source_start + size]))
        notes.append((cue_index + 1, score, source_start + 1, source_start + size))
    return texts, notes


def format_time(seconds: float, *, fps: int = 30) -> str:
    total = int(seconds)
    frame = round((seconds - total) * fps)
    if frame >= fps:
        total += 1
        frame = 0
    hours = total // 3600
    minutes = (total % 3600) // 60
    secs = total % 60
    return f"{hours:02d}:{minutes:02d}:{secs:02d}:{frame:02d}"


def default_txt_path(path: Path) -> Path:
    name = path.name
    if name.endswith(".baseline.txt"):
        return path.with_name(name[: -len(".baseline.txt")] + ".txt")
    return path.with_suffix(".txt")


def main() -> int:
    args = parse_args()
    offset = parse_offset(args.offset)
    cues = parse_srt(args.srt)

    notes: list[tuple[int, float, int, int]] = []
    if args.source and not args.ocr_text:
        source_lines = slice_source(
            read_source_lines(args.source),
            start_marker=args.start_marker,
            end_marker=args.end_marker,
            end_text=args.end_text,
        )
        texts, notes = align_source_to_cues(
            cues,
            source_lines,
            max_source_lines_per_cue=args.max_source_lines_per_cue,
        )
        cues = cues[: len(texts)]
    else:
        texts = [cue.text for cue in cues]

    corrections = read_corrections(args.corrections)
    layout_prefixes = read_layout_prefixes(args.blank_lines_from)
    output_lines = []
    for cue, text in zip(cues, texts, strict=True):
        start_time = format_time(cue.start + offset)
        end_time = format_time(cue.end + offset)
        text = corrections.get(start_time, text)
        clean = clean_text(text, taiwan_variants=args.taiwan_variants)
        if output_lines:
            output_lines.extend(layout_prefixes.get(start_time, []))
        output_lines.append(f"{start_time}\t{end_time}\t{clean}")

    args.out_baseline.parent.mkdir(parents=True, exist_ok=True)
    content = "\n".join(output_lines) + "\n"
    args.out_baseline.write_text(content, encoding="utf-8")
    out_txt = args.out_txt or default_txt_path(args.out_baseline)
    out_txt.write_text(content, encoding="utf-8")

    if args.notes:
        note_lines = [
            f"cue {cue_index}: score {score:.1f}, source lines {first}-{last}"
            for cue_index, score, first, last in notes
            if score < args.min_note_score
        ]
        args.notes.write_text("\n".join(note_lines) + ("\n" if note_lines else ""), encoding="utf-8")

    print(f"wrote {len(cues)} OCR-grouped rows")
    print(args.out_baseline)
    print(out_txt)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
