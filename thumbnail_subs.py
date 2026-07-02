#!/usr/bin/env python3
"""Export a subtitle DOCX thumbnail image using its English YouTube title."""

from __future__ import annotations

import argparse
import posixpath
import re
import sys
from pathlib import Path
from zipfile import ZipFile
import xml.etree.ElementTree as ET


WORD_NS = "http://schemas.openxmlformats.org/wordprocessingml/2006/main"
DRAWING_NS = "http://schemas.openxmlformats.org/drawingml/2006/main"
REL_NS = "http://schemas.openxmlformats.org/officeDocument/2006/relationships"
PKG_REL_NS = "http://schemas.openxmlformats.org/package/2006/relationships"
NS = {"w": WORD_NS, "a": DRAWING_NS, "r": REL_NS, "rel": PKG_REL_NS}
YT_TITLE_LABELS = (
    "建議YT標題：",
    "建議YT標題:",
    "YT_TITLE_SUGGESTED:",
)
TRAILING_PAREN_RE = re.compile(r"\s*[\(（][^()（）]*[\)）]\s*$")
UNSAFE_FILENAME_RE = re.compile(r'[<>:"/\\|?*\x00-\x1f]')


def _paragraph_texts(docx_path: Path) -> list[str]:
    with ZipFile(docx_path) as docx:
        root = ET.fromstring(docx.read("word/document.xml"))

    texts: list[str] = []
    for paragraph in root.findall(".//w:body/w:p", NS):
        text = "".join(node.text or "" for node in paragraph.findall(".//w:t", NS))
        texts.append(text.strip())
    return texts


def english_youtube_title(title: str) -> str:
    title = TRAILING_PAREN_RE.sub("", title.strip()).strip()
    if not title:
        raise ValueError("YouTube title has no English portion.")
    return title


def youtube_title_for_docx(docx_path: Path) -> str:
    texts = _paragraph_texts(docx_path)
    for idx, text in enumerate(texts):
        for label in YT_TITLE_LABELS:
            if text == label:
                for candidate in texts[idx + 1 :]:
                    if candidate:
                        return candidate
            if text.startswith(label):
                candidate = text[len(label) :].strip()
                if candidate:
                    return candidate
    raise ValueError(f"no YouTube title found in {docx_path}")


def thumbnail_stem_for_docx(docx_path: Path) -> str:
    return sanitize_filename(english_youtube_title(youtube_title_for_docx(docx_path)))


def sanitize_filename(value: str) -> str:
    cleaned = UNSAFE_FILENAME_RE.sub("_", value)
    cleaned = re.sub(r"\s+", " ", cleaned).strip(" .")
    if not cleaned:
        raise ValueError("thumbnail filename is empty after sanitizing.")
    return cleaned


def _relationships_by_id(docx: ZipFile) -> dict[str, str]:
    try:
        root = ET.fromstring(docx.read("word/_rels/document.xml.rels"))
    except KeyError:
        return {}

    relationships: dict[str, str] = {}
    for rel in root.findall(".//rel:Relationship", NS):
        rel_id = rel.get("Id")
        target = rel.get("Target")
        if rel_id and target:
            relationships[rel_id] = target
    return relationships


def _first_document_image_name(docx: ZipFile) -> str | None:
    root = ET.fromstring(docx.read("word/document.xml"))
    relationships = _relationships_by_id(docx)
    for blip in root.findall(".//a:blip", NS):
        rel_id = blip.get(f"{{{REL_NS}}}embed")
        if not rel_id:
            continue
        target = relationships.get(rel_id)
        if not target:
            continue
        image_name = posixpath.normpath(posixpath.join("word", target))
        if image_name in docx.namelist():
            return image_name
    return None


def export_thumbnail_from_docx(docx_path: Path, output_dir: Path | None = None) -> Path:
    output_dir = output_dir or docx_path.parent
    stem = thumbnail_stem_for_docx(docx_path)
    with ZipFile(docx_path) as docx:
        image_name = _first_document_image_name(docx)
        if image_name is None:
            raise ValueError(f"no document image found in {docx_path}")
        suffix = Path(image_name).suffix.lower()
        output_path = output_dir / f"{stem}{suffix}"
        output_path.write_bytes(docx.read(image_name))
    return output_path


def parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        prog="thumbnail_subs.py",
        description="Export the first DOCX image using the English YouTube title.",
    )
    parser.add_argument("paths", nargs="+", type=Path, help="DOCX files to process.")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(sys.argv[1:] if argv is None else argv)
    exit_code = 0
    for path in args.paths:
        try:
            output_path = export_thumbnail_from_docx(path)
        except ValueError as exc:
            print(f"[skip] {exc}", file=sys.stderr)
            exit_code = 1
            continue
        print(f"[thumbnail] {output_path}")
    return exit_code


if __name__ == "__main__":
    raise SystemExit(main())
