from pathlib import Path
import tempfile
import unittest
from unittest import mock

import clean_subs
from docx import Document
from docx.oxml import OxmlElement
from docx.oxml.ns import qn


def _shade_paragraph(paragraph, fill: str) -> None:
    p_pr = paragraph._p.get_or_add_pPr()
    shd = OxmlElement("w:shd")
    shd.set(qn("w:val"), "clear")
    shd.set(qn("w:color"), "auto")
    shd.set(qn("w:fill"), fill)
    p_pr.append(shd)


class CleanSubsCliTest(unittest.TestCase):
    def test_resolve_input_paths_uses_current_directory_docx_when_empty(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            tmp_path = Path(tmp_dir)
            first = tmp_path / "a.docx"
            second = tmp_path / "b.docx"
            ignored = tmp_path / "notes.txt"
            first.touch()
            second.touch()
            ignored.touch()

            with mock.patch("clean_subs.Path.cwd", return_value=tmp_path):
                self.assertEqual(
                    clean_subs._resolve_input_paths([]),
                    [first, second],
                )

    def test_resolve_input_paths_keeps_explicit_files(self):
        self.assertEqual(
            clean_subs._resolve_input_paths(["one.docx", "two.docx"]),
            [Path("one.docx"), Path("two.docx")],
        )

    def test_remove_sources_removes_shaded_paragraphs(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            input_path = Path(tmp_dir) / "input.docx"
            output_path = Path(tmp_dir) / "output.docx"
            doc = Document()
            doc.add_paragraph("keep this line")
            shaded = doc.add_paragraph("remove this marked line")
            _shade_paragraph(shaded, "FF0000")
            doc.add_paragraph("keep this too")
            doc.save(input_path)

            clean_subs.remove_sources_from_docx(input_path, output_path)

            cleaned_text = "\n".join(
                paragraph.text for paragraph in Document(output_path).paragraphs
            )
            self.assertIn("keep this line", cleaned_text)
            self.assertIn("keep this too", cleaned_text)
            self.assertNotIn("remove this marked line", cleaned_text)


if __name__ == "__main__":
    unittest.main()
