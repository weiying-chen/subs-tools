from pathlib import Path
import tempfile
import unittest
from unittest import mock
from zipfile import ZIP_DEFLATED, ZipFile

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


def _highlight_run(run, value: str) -> None:
    r_pr = run._r.get_or_add_rPr()
    highlight = OxmlElement("w:highlight")
    highlight.set(qn("w:val"), value)
    r_pr.append(highlight)


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

    def test_remove_sources_preserves_shaded_paragraphs(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            input_path = Path(tmp_dir) / "input.docx"
            output_path = Path(tmp_dir) / "output.docx"
            doc = Document()
            doc.add_paragraph("keep this line")
            shaded = doc.add_paragraph("keep this marked line")
            _shade_paragraph(shaded, "FF0000")
            doc.add_paragraph("keep this too")
            doc.save(input_path)

            clean_subs.remove_sources_from_docx(input_path, output_path)

            cleaned_text = "\n".join(
                paragraph.text for paragraph in Document(output_path).paragraphs
            )
            self.assertIn("keep this line", cleaned_text)
            self.assertIn("keep this marked line", cleaned_text)
            self.assertIn("keep this too", cleaned_text)

    def test_remove_sources_strips_highlight_and_shading_formatting(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            input_path = Path(tmp_dir) / "input.docx"
            output_path = Path(tmp_dir) / "output.docx"
            doc = Document()
            summary = doc.add_paragraph()
            summary_run = summary.add_run("(1)04:10-06:52 (2m42s)")
            _highlight_run(summary_run, "yellow")
            doc.add_paragraph("字幕：")
            shaded = doc.add_paragraph("keep shaded text")
            _shade_paragraph(shaded, "FF0000")
            highlighted = doc.add_paragraph()
            run = highlighted.add_run("keep highlighted text")
            _highlight_run(run, "yellow")
            doc.save(input_path)

            clean_subs.remove_sources_from_docx(input_path, output_path)

            output_doc = Document(output_path)
            cleaned_text = "\n".join(paragraph.text for paragraph in output_doc.paragraphs)
            self.assertIn("(1)04:10-06:52 (2m42s)", cleaned_text)
            self.assertIn("keep shaded text", cleaned_text)
            self.assertIn("keep highlighted text", cleaned_text)
            self.assertTrue(output_doc.paragraphs[0]._p.findall(".//w:highlight", {"w": clean_subs.WORD_NAMESPACE}))
            for paragraph in output_doc.paragraphs[2:]:
                self.assertFalse(paragraph._p.findall(".//w:shd", {"w": clean_subs.WORD_NAMESPACE}))
                self.assertFalse(paragraph._p.findall(".//w:highlight", {"w": clean_subs.WORD_NAMESPACE}))

    def test_repair_missing_use_local_dpi_namespace(self):
        broken_xml = (
            b'<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
            b'<w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main">'
            b"<w:body><w:p><w:r><w:drawing><ns6:useLocalDpi val=\"0\"/>"
            b"</w:drawing></w:r></w:p></w:body></w:document>"
        )

        repaired_xml = clean_subs._repair_word_xml_namespaces(broken_xml)

        self.assertIn(b'xmlns:ns6="http://schemas.microsoft.com/office/drawing/2010/main"', repaired_xml)

    def test_normalize_preserves_repaired_use_local_dpi_namespace(self):
        original_xml = (
            b'<w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main">'
            b"<w:body/></w:document>"
        )
        cleaned_xml = (
            b'<w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main" '
            b'xmlns:ns6="http://schemas.microsoft.com/office/drawing/2010/main">'
            b"<w:body><ns6:useLocalDpi val=\"0\"/></w:body></w:document>"
        )

        normalized_xml = clean_subs._normalize_xml_part_against_original(
            cleaned_xml,
            original_xml,
        )

        self.assertIn(b'xmlns:ns6="http://schemas.microsoft.com/office/drawing/2010/main"', normalized_xml)

    def test_remove_sources_turns_off_track_changes(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            input_path = Path(tmp_dir) / "input.docx"
            output_path = Path(tmp_dir) / "output.docx"
            doc = Document()
            doc.add_paragraph("keep this line")
            doc.save(input_path)

            with ZipFile(input_path, "a", compression=ZIP_DEFLATED) as docx:
                settings_xml = docx.read("word/settings.xml")
                settings_xml = settings_xml.replace(
                    b"<w:defaultTabStop",
                    b"<w:trackRevisions/><w:defaultTabStop",
                    1,
                )
                docx.writestr("word/settings.xml", settings_xml)

            clean_subs.remove_sources_from_docx(input_path, output_path)

            with ZipFile(output_path, "r") as docx:
                self.assertNotIn(b"<w:trackRevisions", docx.read("word/settings.xml"))


if __name__ == "__main__":
    unittest.main()
