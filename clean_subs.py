#!/usr/bin/env python3

from __future__ import annotations

import argparse
from pathlib import Path

from docx import Document


def remove_sources_from_docx(input_path: Path, output_path: Path) -> None:
    doc = Document(str(input_path))
    output_path.parent.mkdir(parents=True, exist_ok=True)
    doc.save(str(output_path))


def _default_output_path(path: Path) -> Path:
    return path.with_name(f"{path.stem}_nosource{path.suffix}")


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Write cleaned DOCX files."
    )
    parser.add_argument("docx_files", nargs="+", help="Input DOCX file paths.")
    parser.add_argument(
        "--in-place",
        action="store_true",
        help="Overwrite input files instead of creating _nosource copies.",
    )
    args = parser.parse_args()

    for raw_path in args.docx_files:
        input_path = Path(raw_path)
        output_path = input_path if args.in_place else _default_output_path(input_path)
        remove_sources_from_docx(input_path, output_path)


if __name__ == "__main__":
    main()
