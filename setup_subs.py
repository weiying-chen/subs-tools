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
# Some files keep subtitle rows as full lines in paragraph text.
PARAGRAPH_TAB_LINE_RE = re.compile(
    r"^(\d{2}:\d{2}:\d{2}:\d{2})\t+(\d{2}:\d{2}:\d{2}:\d{2})\t+(.+)$"
)
PARAGRAPH_COMPACT_LINE_RE = re.compile(
    r"^(\d{2}:\d{2}:\d{2}:\d{2})(\d{2}:\d{2}:\d{2}:\d{2})(.+)$"
)
HAS_CHINESE_RE = re.compile(r"[\u4e00-\u9fff]")


def load_docx_root(docx_path: Path) -> ET.Element:
    with zipfile.ZipFile(docx_path) as zf:
        xml = zf.read("word/document.xml")
    return ET.fromstring(xml)


def paragraph_text_with_tabs(para: ET.Element) -> str:
    parts: list[str] = []
    for node in para.iter():
        if node.tag == f"{{{W_NS}}}tab":
            parts.append("\t")
        elif node.tag == f"{{{W_NS}}}t":
            parts.append(node.text or "")
    return "".join(parts).strip()


def run_is_yellow(run: ET.Element) -> bool:
    hl = run.find("./w:rPr/w:highlight", NS)
    return hl is not None and hl.attrib.get(f"{{{W_NS}}}val") == "yellow"


def yellow_paragraph_text_with_tabs(para: ET.Element) -> str:
    parts: list[str] = []
    for run in para.findall(".//w:r", NS):
        if not run_is_yellow(run):
            continue
        for node in run.iter():
            if node.tag == f"{{{W_NS}}}tab":
                parts.append("\t")
            elif node.tag == f"{{{W_NS}}}t":
                parts.append(node.text or "")
    return "".join(parts).strip()


def normalize_compact_text(text: str) -> str:
    # Normalize BOM/zero-width/no-break characters frequently found in Word runs.
    return (
        text.replace("\ufeff", "")
        .replace("\u200b", "")
        .replace("\u00a0", " ")
        .replace(" ", "")
    )


def extract_ts_lines_from_yellow(root: ET.Element) -> list[str]:
    out: list[str] = []

    for para in root.findall(".//w:p", NS):
        text = yellow_paragraph_text_with_tabs(para)
        if not text:
            continue

        parsed = parse_paragraph_row(text)
        if parsed is None:
            continue

        start, end, zh = parsed
        if not HAS_CHINESE_RE.search(zh):
            continue

        out.append(f"{start}\t{end}\t{zh}")

    return out


def parse_paragraph_row(text: str) -> tuple[str, str, str] | None:
    tab_match = PARAGRAPH_TAB_LINE_RE.match(text)
    if tab_match:
        return tab_match.group(1), tab_match.group(2), tab_match.group(3)

    # Fallback for compact rows where docx text is concatenated without tabs.
    normalized = normalize_compact_text(text)
    compact_match = PARAGRAPH_COMPACT_LINE_RE.match(normalized)
    if compact_match:
        return compact_match.group(1), compact_match.group(2), compact_match.group(3)

    return None


def extract_ts_lines_from_paragraphs_with_any_yellow(root: ET.Element) -> list[str]:
    out: list[str] = []

    for para in root.findall(".//w:p", NS):
        has_yellow = any(run_is_yellow(run) for run in para.findall('.//w:r', NS))
        if not has_yellow:
            continue

        text = paragraph_text_with_tabs(para)
        if not text:
            continue

        parsed = parse_paragraph_row(text)
        if parsed is None:
            continue

        start, end, zh = parsed
        if not HAS_CHINESE_RE.search(zh):
            continue

        out.append(f"{start}\t{end}\t{zh}")

    return out


def extract_ts_lines_from_all_paragraphs(root: ET.Element) -> list[str]:
    out: list[str] = []

    for para in root.findall(".//w:p", NS):
        text = paragraph_text_with_tabs(para)
        if not text:
            continue

        parsed = parse_paragraph_row(text)
        if parsed is None:
            continue

        start, end, zh = parsed
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

    # auto: prefer yellow-highlighted extraction, and keep rows from
    # paragraphs that contain yellow runs (for partial-highlight rows).
    yellow_lines = extract_ts_lines_from_yellow(root)
    if not yellow_lines:
        return extract_ts_lines_from_all_paragraphs(root)

    para_yellow_lines = extract_ts_lines_from_paragraphs_with_any_yellow(root)
    merged: list[str] = []
    seen: set[str] = set()
    for line in para_yellow_lines + yellow_lines:
        if line in seen:
            continue
        seen.add(line)
        merged.append(line)
    return merged


def render_output_content(lines: list[str], *, is_baseline: bool) -> str:
    if is_baseline:
        return "\n".join(lines) + ("\n" if lines else "")

    sections = [
        "YT_TITLE_SUGGESTED:",
        "",
        "TITLE_SUGGESTED:",
        "",
        "INTRO:",
        "",
        "THUMBNAIL:",
        "",
        "BODY:",
    ]
    body = "\n".join(lines)
    content = "\n".join(sections)
    if body:
        content = f"{content}\n\n{body}"
    return content + "\n"


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
            out.extend(
                sorted(
                    docx_path
                    for docx_path in p.glob("*.docx")
                    if not docx_path.name.startswith("~$")
                )
            )
        elif p.is_file() and p.suffix.lower() == ".docx":
            if p.name.startswith("~$"):
                continue
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
        try:
            lines = extract_ts_lines(docx_path, mode=args.mode)
        except (zipfile.BadZipFile, KeyError, ET.ParseError) as exc:
            print(f"[skip] invalid docx: {docx_path} ({exc})")
            continue

        out_paths: list[Path] = []
        if args.out in ("both", "txt"):
            out_paths.append(docx_path.with_suffix(".txt"))
        if args.out in ("both", "baseline"):
            out_paths.append(docx_path.with_suffix(".baseline.txt"))

        for out_path in out_paths:
            if out_path.exists() and not args.force:
                print(f"[skip] exists: {out_path}")
                continue
            content = render_output_content(
                lines, is_baseline=out_path.name.endswith(".baseline.txt")
            )
            out_path.write_text(content, encoding="utf-8")
            print(f"[wrote] {out_path} ({len(lines)} lines)")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
