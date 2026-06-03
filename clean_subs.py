#!/usr/bin/env python3

from __future__ import annotations

import argparse
from io import BytesIO
from pathlib import Path
from zipfile import ZIP_DEFLATED, ZipFile
import xml.etree.ElementTree as ET

from docx import Document


INDENT_THRESHOLD_PT = 21.0
WORD_NAMESPACE = "http://schemas.openxmlformats.org/wordprocessingml/2006/main"
INSERTION_TAGS = {f"{{{WORD_NAMESPACE}}}ins", f"{{{WORD_NAMESPACE}}}moveTo"}
DELETION_TAGS = {f"{{{WORD_NAMESPACE}}}del", f"{{{WORD_NAMESPACE}}}moveFrom"}
CHANGE_TAGS = {
    f"{{{WORD_NAMESPACE}}}pPrChange",
    f"{{{WORD_NAMESPACE}}}rPrChange",
    f"{{{WORD_NAMESPACE}}}tblPrChange",
    f"{{{WORD_NAMESPACE}}}tcPrChange",
    f"{{{WORD_NAMESPACE}}}trPrChange",
    f"{{{WORD_NAMESPACE}}}moveFromRangeStart",
    f"{{{WORD_NAMESPACE}}}moveFromRangeEnd",
    f"{{{WORD_NAMESPACE}}}moveToRangeStart",
    f"{{{WORD_NAMESPACE}}}moveToRangeEnd",
}


def _remove_paragraph(paragraph) -> None:
    element = paragraph._element
    parent = element.getparent()
    if parent is not None:
        parent.remove(element)


def _left_indent_pt(paragraph) -> float | None:
    indent = paragraph.paragraph_format.left_indent
    if indent is not None:
        return indent.pt
    style = paragraph.style
    if style is None or style.paragraph_format is None:
        return None
    style_indent = style.paragraph_format.left_indent
    if style_indent is None:
        return None
    return style_indent.pt


def _is_indented_content_paragraph(paragraph) -> bool:
    if not paragraph.text.strip():
        return False
    left_indent = _left_indent_pt(paragraph)
    return left_indent is not None and left_indent >= INDENT_THRESHOLD_PT


def _rewrite_revision_children(element) -> bool:
    changed = False
    idx = 0
    while idx < len(element):
        child = element[idx]
        if child.tag in INSERTION_TAGS:
            grandchildren = list(child)
            element.remove(child)
            for offset, grandchild in enumerate(grandchildren):
                element.insert(idx + offset, grandchild)
            changed = True
            idx += len(grandchildren)
            continue
        if child.tag in DELETION_TAGS or child.tag in CHANGE_TAGS:
            element.remove(child)
            changed = True
            continue
        if _rewrite_revision_children(child):
            changed = True
        idx += 1
    return changed


def _accept_revisions_in_tree(root) -> None:
    while _rewrite_revision_children(root):
        pass


def _accepted_revisions_docx_bytes(input_path: Path) -> bytes:
    buffer = BytesIO()
    with ZipFile(input_path, "r") as zin, ZipFile(buffer, "w", compression=ZIP_DEFLATED) as zout:
        for info in zin.infolist():
            data = zin.read(info.filename)
            if info.filename.startswith("word/") and info.filename.endswith(".xml"):
                root = ET.fromstring(data)
                _accept_revisions_in_tree(root)
                data = ET.tostring(root, encoding="utf-8", xml_declaration=True)
            zout.writestr(info, data)
    return buffer.getvalue()


def remove_sources_from_docx(input_path: Path, output_path: Path) -> None:
    doc = Document(BytesIO(_accepted_revisions_docx_bytes(input_path)))
    paragraphs = list(doc.paragraphs)
    remove_indexes = {
        idx for idx, paragraph in enumerate(paragraphs) if _is_indented_content_paragraph(paragraph)
    }
    if remove_indexes:
        block_starts = sorted(remove_indexes)
        block_ranges: list[tuple[int, int]] = []
        start = end = block_starts[0]
        for idx in block_starts[1:]:
            if idx == end + 1:
                end = idx
                continue
            block_ranges.append((start, end))
            start = end = idx
        block_ranges.append((start, end))

        for start, end in block_ranges:
            prev_idx = start - 1
            while prev_idx >= 0 and not paragraphs[prev_idx].text.strip():
                remove_indexes.add(prev_idx)
                prev_idx -= 1

            next_idx = end + 1
            while next_idx < len(paragraphs) and not paragraphs[next_idx].text.strip():
                remove_indexes.add(next_idx)
                next_idx += 1

    for index in sorted(remove_indexes, reverse=True):
        _remove_paragraph(paragraphs[index])

    paragraphs = list(doc.paragraphs)
    blank_indexes = []
    for idx, paragraph in enumerate(paragraphs):
        if paragraph.text.strip():
            continue
        prev_non_blank = None
        next_non_blank = None
        for prev_idx in range(idx - 1, -1, -1):
            if paragraphs[prev_idx].text.strip():
                prev_non_blank = paragraphs[prev_idx]
                break
        for next_idx in range(idx + 1, len(paragraphs)):
            if paragraphs[next_idx].text.strip():
                next_non_blank = paragraphs[next_idx]
                break
        if prev_non_blank is None or next_non_blank is None:
            continue
        if _left_indent_pt(paragraph) is None:
            continue
        blank_indexes.append(idx)

    for index in reversed(blank_indexes):
        _remove_paragraph(paragraphs[index])

    output_path.parent.mkdir(parents=True, exist_ok=True)
    doc.save(str(output_path))


def _resolve_output_path(input_path: Path, output_path: str | None) -> Path:
    if output_path:
        return Path(output_path)
    return input_path


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Write cleaned DOCX files."
    )
    parser.add_argument("docx_files", nargs="+", help="Input DOCX file paths.")
    parser.add_argument(
        "--output",
        help="Write cleaned content to a separate DOCX path. Default: overwrite input.",
    )
    args = parser.parse_args()

    if args.output and len(args.docx_files) != 1:
        parser.error("--output requires exactly one input DOCX file.")

    for raw_path in args.docx_files:
        input_path = Path(raw_path)
        output_path = _resolve_output_path(input_path, args.output)
        remove_sources_from_docx(input_path, output_path)


if __name__ == "__main__":
    main()
