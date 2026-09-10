#!/usr/bin/env python3
from __future__ import annotations

import argparse
import re
import sys
import xml.etree.ElementTree as ET
from dataclasses import dataclass
from difflib import SequenceMatcher
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
            "OCR cues set timing; identical touching cues merge after text correction."
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
            "before identical touching cues are merged, retaining their outer timestamps."
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
    time_offset: float = 0.0,
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
    issues: list[str] = []
    for cue_index, source_start, size, score in items:
        assigned = source_lines[source_start : source_start + size]
        missing = unsupported_source_lines(cues[cue_index].text, assigned)
        if missing is None:
            check_ocr_text_changes(
                cues[cue_index].text, "".join(assigned), cues[cue_index].start + time_offset
            )
        if missing is not None:
            first, last = missing
            cue = cues[cue_index]
            detail = (
                f"cue {cue_index + 1} at {format_time(cue.start + time_offset)}: "
                f"source lines {source_start + first + 1}-{source_start + last} "
                f"are absent from OCR: {' / '.join(assigned[first:last])!r}"
            )
            # Gaps are review locations, not inferred subtitle timings.
            if first == 0 and cue_index > 0 and cues[cue_index - 1].end < cue.start:
                detail += (
                    f"; preceding gap {format_time(cues[cue_index - 1].end + time_offset)}"
                    f"–{format_time(cue.start + time_offset)}"
                )
            if last == size and cue_index + 1 < len(cues) and cue.end < cues[cue_index + 1].start:
                detail += (
                    f"; following gap {format_time(cue.end + time_offset)}"
                    f"–{format_time(cues[cue_index + 1].start + time_offset)}"
                )
            issues.append(detail)
        texts.append("".join(assigned))
        notes.append((cue_index + 1, score, source_start + 1, source_start + size))
    if issues:
        raise ValueError(
            "Possible missing OCR segment(s); refusing to merge unsupported source text.\n"
            + "\n".join(issues)
            + "\nCheck the saved frames and correct the input SRT before rerunning. "
            "No output files were written."
        )
    return texts, notes


def check_ocr_text_changes(ocr_text: str, proposed: str, start: float) -> None:
    """Flag inserted/deleted characters, allowing equal-length glyph corrections.

    Formatting and known OCR noise are normalized first. Even a single added
    particle requires frame review; unequal-length replacements are ambiguous
    and also require review. This is not a semantic check of substitutions.
    """
    original = normalize_for_match(clean_text(ocr_text, taiwan_variants=True))
    revised = normalize_for_match(clean_text(proposed, taiwan_variants=True))
    # Anchor matching edges before diffing so repeated characters do not shift
    # the reported deletion away from the phrase actually removed.
    prefix = 0
    while prefix < min(len(original), len(revised)) and original[prefix] == revised[prefix]:
        prefix += 1
    original, revised = original[prefix:], revised[prefix:]
    while original and revised and original[-1] == revised[-1]:
        original, revised = original[:-1], revised[:-1]
    changes: list[str] = []
    for tag, first, last, new_first, new_last in SequenceMatcher(
        None, original, revised, autojunk=False
    ).get_opcodes():
        old, new = original[first:last], revised[new_first:new_last]
        old_count = sum(c.isalnum() for c in old)
        new_count = sum(c.isalnum() for c in new)
        if tag == "insert" and new_count:
            changes.append(f"added {new!r}")
        elif tag == "delete" and old_count:
            changes.append(f"removed {old!r}")
        elif tag == "replace" and old_count != new_count:
            changes.append(f"changed length: {old!r} -> {new!r}")
    if changes:
        raise ValueError(
            f"OCR character changes require frame review at {format_time(start)}: "
            + "; ".join(changes)
            + ". Check the saved frame, source section boundary, and corrections TSV; "
            "make source/corrections match the visible subtitle, or restore OCR omissions "
            "in the input SRT after checking the frame. No output files were written."
        )


def unsupported_source_lines(ocr_text: str, assigned: list[str]) -> tuple[int, int] | None:
    """Detect whole extra lines when the remaining source exactly matches OCR.

    Normalization permits punctuation and common variant differences. This is
    deliberately conservative: ordinary character corrections and fully
    supported multi-line groups remain valid. A suspected omission requires
    frame review because OCR text alone cannot establish a new cue's timing.
    """
    expected = normalize_for_match(ocr_text)
    parts = [normalize_for_match(line) for line in assigned]
    if not expected or "".join(parts) == expected:
        return None
    for first in range(len(parts)):
        for last in range(first + 1, len(parts) + 1):
            if "".join(parts[first:last]) and "".join(parts[:first] + parts[last:]) == expected:
                return first, last
    return None


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


def merge_duplicate_cues(
    cues: list[Cue], *, preserve_starts: set[float] | None = None
) -> list[Cue]:
    """Coalesce exact corrected duplicates only across touching time boundaries.

    OCR background noise can split one displayed subtitle into several cues.
    Once corrected, those cues share identical text. Do not use fuzzy matching
    here, bridge gaps/overlaps, or remove boundaries carrying saved annotations.
    """
    boundaries = preserve_starts or set()
    merged: list[Cue] = []
    for cue in cues:
        if (
            merged
            and cue.text
            and cue.text == merged[-1].text
            and abs(cue.start - merged[-1].end) <= 1e-6
            and cue.start not in boundaries
        ):
            merged[-1] = Cue(merged[-1].start, cue.end, merged[-1].text)
        else:
            merged.append(cue)
    return merged


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
        try:
            texts, notes = align_source_to_cues(
                cues,
                source_lines,
                max_source_lines_per_cue=args.max_source_lines_per_cue,
                time_offset=offset,
            )
        except ValueError as error:
            print(f"error: {error}", file=sys.stderr)
            return 1
        cues = cues[: len(texts)]
    else:
        texts = [cue.text for cue in cues]

    corrections = read_corrections(args.corrections)
    layout_prefixes = read_layout_prefixes(args.blank_lines_from)
    corrected_cues: list[Cue] = []
    for cue, text in zip(cues, texts, strict=True):
        start_time = format_time(cue.start + offset)
        text = corrections.get(start_time, text)
        clean = clean_text(text, taiwan_variants=args.taiwan_variants)
        try:
            check_ocr_text_changes(cue.text, clean, cue.start + offset)
        except ValueError as error:
            print(f"error: {error}", file=sys.stderr)
            return 1
        corrected_cues.append(Cue(cue.start, cue.end, clean))

    preserve_starts = {
        cue.start for cue in corrected_cues
        if layout_prefixes.get(format_time(cue.start + offset))
    }
    merged_cues = merge_duplicate_cues(corrected_cues, preserve_starts=preserve_starts)
    output_lines = []
    for cue in merged_cues:
        start_time = format_time(cue.start + offset)
        end_time = format_time(cue.end + offset)
        if output_lines:
            output_lines.extend(layout_prefixes.get(start_time, []))
        output_lines.append(f"{start_time}\t{end_time}\t{cue.text}")

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

    print(
        f"wrote {len(merged_cues)} rows from {len(corrected_cues)} OCR cues; "
        f"merged {len(corrected_cues) - len(merged_cues)} adjacent duplicate cues"
    )
    print(args.out_baseline)
    print(out_txt)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
