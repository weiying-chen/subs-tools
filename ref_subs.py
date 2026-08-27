#!/usr/bin/env python3
"""Build paired pre-edit/post-edit subtitle reference bundles."""

from __future__ import annotations

import argparse
import re
import sys
import xml.etree.ElementTree as ET
import zipfile
from dataclasses import dataclass
from pathlib import Path

from thumbnail_subs import english_youtube_title, sanitize_filename


DEFAULT_ROOT = Path.home() / "text" / "subs"
W_NS = "http://schemas.openxmlformats.org/wordprocessingml/2006/main"
W = f"{{{W_NS}}}"
DATE_RE = re.compile(r"(?<!\d)(20\d{6})(?!\d)")
LABELS = {
    "youtube": {"建議YT標題：", "建議YT標題:", "YT_TITLE_SUGGESTED:"},
    "title": {"建議標題：", "建議標題:", "TITLE_SUGGESTED:"},
    "intro": {"簡介：", "簡介:", "INTRO:"},
    "thumbnail": {"選圖：", "選圖:", "縮圖：", "縮圖:", "THUMBNAIL:"},
    "body": {"字幕：", "字幕:", "BODY:"},
}


@dataclass(frozen=True)
class Pair:
    key: str
    pre: Path
    post: Path


def discover_sources(root: Path) -> list[Path]:
    return sorted(
        path
        for path in root.iterdir()
        if path.is_dir()
        and (path / "output").is_dir()
        and (path / "edited").is_dir()
    )


def normalized_stem(path: Path, suffix: str) -> str:
    stem = path.stem
    return stem[: -len(suffix)] if stem.endswith(suffix) else stem


def discover_pairs(
    sources: Path | list[Path], series: str | None = None
) -> list[Pair]:
    if isinstance(sources, Path):
        sources = [sources]
    pairs: list[Pair] = []
    for source in sources:
        pairs.extend(discover_source_pairs(source, series))
    return sorted(pairs, key=lambda pair: pair.key)


def discover_source_pairs(source: Path, series: str | None = None) -> list[Pair]:
    output = source / "output"
    edited = source / "edited"
    pre_by_key = {
        normalized_stem(path, "_al"): path
        for path in output.glob("*_al.docx")
        if not path.name.startswith("~$")
    }
    post_by_key = {
        normalized_stem(path, "_final"): path
        for path in edited.glob("*_final.docx")
        if not path.name.startswith("~$")
    }
    return [
        Pair(key, pre_by_key[key], post_by_key[key])
        for key in sorted(pre_by_key.keys() & post_by_key.keys())
        if series is None or series in key
    ]


def pair_date(pair: Pair) -> tuple[int, str]:
    match = DATE_RE.search(pair.key)
    return (int(match.group(1)) if match else 0, pair.key)


def latest_pairs(pairs: list[Pair], limit: int = 4, fallback: int = 3) -> list[Pair]:
    ordered = sorted(pairs, key=pair_date)
    count = limit if len(ordered) >= limit else min(fallback, len(ordered))
    return ordered[-count:]


def docx_paragraphs(path: Path) -> list[str]:
    with zipfile.ZipFile(path) as archive:
        root = ET.fromstring(archive.read("word/document.xml"))
    paragraphs: list[str] = []
    for paragraph in root.iter(W + "p"):
        parts: list[str] = []
        for node in paragraph.iter():
            if node.tag == W + "t":
                parts.append(node.text or "")
            elif node.tag == W + "tab":
                parts.append("\t")
            elif node.tag in {W + "br", W + "cr"}:
                parts.append("\n")
        paragraphs.append("".join(parts).strip())
    return paragraphs


def label_index(lines: list[str], kind: str) -> int:
    for index, line in enumerate(lines):
        if line in LABELS[kind]:
            return index
    raise ValueError(f"missing {kind} label")


def next_nonempty(lines: list[str], start: int) -> str:
    for line in lines[start + 1 :]:
        if line:
            return line
    return ""


def normalized_lines(lines: list[str]) -> list[str]:
    output: list[str] = []
    for line in lines:
        if not line and (not output or not output[-1]):
            continue
        output.append(line)
    while output and not output[-1]:
        output.pop()
    return output


def docx_to_txt(path: Path) -> str:
    lines = docx_paragraphs(path)
    youtube_index = label_index(lines, "youtube")
    title_index = label_index(lines, "title")
    intro_index = label_index(lines, "intro")
    thumbnail_index = label_index(lines, "thumbnail")
    body_index = label_index(lines, "body")
    youtube_title = next_nonempty(lines, youtube_index)
    title = next_nonempty(lines, title_index)
    intro = [line for line in lines[intro_index + 1 : thumbnail_index] if line]
    body = normalized_lines(lines[body_index + 1 :])
    thumbnail = sanitize_filename(english_youtube_title(youtube_title)) + ".png"
    rendered = [
        f"YT_TITLE_SUGGESTED: {youtube_title}",
        "",
        f"TITLE_SUGGESTED: {title}",
        "",
        "INTRO:",
        "",
        *sum(([line, ""] for line in intro), []),
        f"THUMBNAIL: {thumbnail}",
        "",
        "BODY:",
        "",
        *body,
    ]
    return "\n".join(rendered).rstrip() + "\n"


def render_bundle(series: str, pairs: list[Pair]) -> str:
    lines = [
        f"# {series} — Latest {len(pairs)}",
        "",
        f"最近 {len(pairs)} 個已完成的{series}項目。每一項依序收錄 `output/` 的 pre-edit "
        "與 `edited/` 的 post-edit，內容均保留標準 TXT 欄位格式。",
    ]
    for pair in pairs:
        lines.extend(
            [
                "",
                "---",
                "",
                f"# {pair.key}",
                "",
                "### Pre-edit (`output/`)",
                "",
                docx_to_txt(pair.pre).rstrip(),
                "",
                "### Post-edit (`edited/`)",
                "",
                docx_to_txt(pair.post).rstrip(),
            ]
        )
    return "\n".join(lines).rstrip() + "\n"


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--series", required=True, help="series name used for the reference folder and heading")
    parser.add_argument("--root", type=Path, default=DEFAULT_ROOT, help=f"subtitle root (default: {DEFAULT_ROOT})")
    parser.add_argument("--check", action="store_true", help="report a stale reference without rewriting it")
    parser.add_argument("--dry-run", action="store_true", help="show the target without rewriting it")
    args = parser.parse_args()

    root = args.root.expanduser().resolve()
    if not root.is_dir():
        print(f"[error] subtitle root not found: {root}", file=sys.stderr)
        return 2
    sources = discover_sources(root)
    pairs = latest_pairs(discover_pairs(sources, series=args.series))
    if len(pairs) < 3:
        print(f"[error] expected at least 3 complete pairs, found {len(pairs)}", file=sys.stderr)
        return 1
    output = root / "refs" / args.series / f"latest-{len(pairs)}.md"
    content = render_bundle(args.series, pairs)
    changed = not output.exists() or output.read_text(encoding="utf-8") != content
    if args.check:
        if changed:
            print(f"stale: {output}", file=sys.stderr)
            return 1
        print("reference file is up to date")
        return 0
    if args.dry_run:
        print(f"would update: {output}" if changed else "reference file is up to date")
        return 0
    output.parent.mkdir(parents=True, exist_ok=True)
    if changed:
        output.write_text(content, encoding="utf-8")
        print(f"updated: {output}")
    else:
        print("reference file is up to date")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
