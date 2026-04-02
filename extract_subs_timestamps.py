#!/usr/bin/env python3
from __future__ import annotations

import argparse
import re
import xml.etree.ElementTree as ET
import zipfile
from pathlib import Path

W_NS = "http://schemas.openxmlformats.org/wordprocessingml/2006/main"
NS = {"w": W_NS}

# In current files, yellow-highlighted runs often store: <start><end><zh_text>
HIGHLIGHTED_LINE_RE = re.compile(
    r"^(\d{2}:\d{2}:\d{2}:\d{2})(\d{2}:\d{2}:\d{2}:\d{2})(.+)$"
)
# Some files keep subtitle rows as full lines in plain paragraph text.
PARAGRAPH_LINE_RE = re.compile(
    r"^(\d{2}:\d{2}:\d{2}:\d{2})\t(\d{2}:\d{2}:\d{2}:\d{2})\t(.+)$"
)
HAS_CHINESE_RE = re.compile(r"[\u4e00-\u9fff]")


def load_docx_root(docx_path: Path) -> ET.Element:
    with zipfile.ZipFile(docx_path) as zf:
        xml = zf.read("word/document.xml")
    return ET.fromstring(xml)


def extract_ts_lines_from_yellow(root: ET.Element) -> list[str]:
    out: list[str] = []

    for run in root.findall(".//w:r", NS):
        hl = run.find("./w:rPr/w:highlight", NS)
        if hl is None or hl.attrib.get(f"{{{W_NS}}}val") != "yellow":
            continue

        text = "".join((t.text or "") for t in run.findall(".//w:t", NS)).strip()
        if not text:
            continue

        # Remove spacing that may appear between concatenated fields.
        normalized = text.replace("\u00a0", " ").replace(" ", "")
        m = HIGHLIGHTED_LINE_RE.match(normalized)
        if not m:
            continue

        start, end, zh = m.group(1), m.group(2), m.group(3)
        if not HAS_CHINESE_RE.search(zh):
            continue

        out.append(f"{start}\t{end}\t{zh}")

    return out


def extract_ts_lines_from_all_paragraphs(root: ET.Element) -> list[str]:
    out: list[str] = []

    for para in root.findall(".//w:p", NS):
        text = "".join((t.text or "") for t in para.findall(".//w:t", NS)).strip()
        if not text:
            continue

        m = PARAGRAPH_LINE_RE.match(text)
        if not m:
            continue

        start, end, zh = m.group(1), m.group(2), m.group(3)
        if not HAS_CHINESE_RE.search(zh):
            continue

        out.append(f"{start}\t{end}\t{zh}")

    return out


def extract_ts_lines(docx_path: Path, mode: str = "auto") -> list[str]:
    root = load_docx_root(docx_path)

    if mode == "yellow":
        return extract_ts_lines_from_yellow(root)

    if mode == "all":
        return extract_ts_lines_from_all_paragraphs(root)

    # auto: prefer yellow-highlighted extraction, then fallback to all lines.
    yellow_lines = extract_ts_lines_from_yellow(root)
    if yellow_lines:
        return yellow_lines
    return extract_ts_lines_from_all_paragraphs(root)


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(
        description=(
            "Extract timestamp rows from docx files. "
            "Default mode prefers yellow-highlighted runs and falls back to all paragraphs."
        )
    )
    p.add_argument(
        "paths",
        nargs="*",
        type=Path,
        help="Docx file(s) or directory(ies). Defaults to current directory.",
    )
    p.add_argument(
        "--force",
        action="store_true",
        help="Overwrite existing outputs.",
    )
    p.add_argument(
        "--out",
        choices=["both", "txt", "baseline"],
        default="both",
        help="Which output files to write.",
    )
    p.add_argument(
        "--mode",
        choices=["auto", "yellow", "all"],
        default="auto",
        help="Extraction mode: auto (yellow then fallback), yellow, or all paragraphs.",
    )
    return p.parse_args()


def gather_docx_paths(paths: list[Path]) -> list[Path]:
    if not paths:
        paths = [Path.cwd()]

    out: list[Path] = []
    for p in paths:
        if p.is_dir():
            out.extend(sorted(p.glob("*.docx")))
        elif p.is_file() and p.suffix.lower() == ".docx":
            out.append(p)

    # de-dup while preserving order
    seen: set[Path] = set()
    uniq: list[Path] = []
    for p in out:
        rp = p.resolve()
        if rp not in seen:
            seen.add(rp)
            uniq.append(p)
    return uniq


def main() -> int:
    args = parse_args()
    docx_paths = gather_docx_paths(args.paths)
    if not docx_paths:
        print("[error] no .docx files found")
        return 2

    for docx_path in docx_paths:
        lines = extract_ts_lines(docx_path, mode=args.mode)
        content = "\n".join(lines) + ("\n" if lines else "")

        out_paths: list[Path] = []
        if args.out in ("both", "txt"):
            out_paths.append(docx_path.with_suffix(".txt"))
        if args.out in ("both", "baseline"):
            out_paths.append(docx_path.with_suffix(".baseline.txt"))

        for out_path in out_paths:
            if out_path.exists() and not args.force:
                print(f"[skip] exists: {out_path}")
                continue
            out_path.write_text(content, encoding="utf-8")
            print(f"[wrote] {out_path} ({len(lines)} lines)")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
