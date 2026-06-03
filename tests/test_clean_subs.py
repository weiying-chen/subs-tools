import tempfile
import unittest
from pathlib import Path
from unittest import mock
from zipfile import ZIP_DEFLATED, ZipFile
import xml.etree.ElementTree as ET

try:
    from docx import Document
    from docx.shared import Pt
except ModuleNotFoundError:
    Document = None
    clean_subs = None
else:
    import clean_subs


@unittest.skipIf(Document is None, "python-docx is not installed")
class CleanSubsTest(unittest.TestCase):
    NS = {"w": "http://schemas.openxmlformats.org/wordprocessingml/2006/main"}

    def _write_docx(
        self,
        path: Path,
        paragraphs: list[str],
        *,
        indented_indexes: set[int] | None = None,
        indent_points_by_index: dict[int, float] | None = None,
    ) -> None:
        doc = Document()
        indented_indexes = indented_indexes or set()
        indent_points_by_index = indent_points_by_index or {}
        for idx, text in enumerate(paragraphs):
            paragraph = doc.add_paragraph(text)
            if idx in indented_indexes:
                paragraph.paragraph_format.left_indent = Pt(24)
            if idx in indent_points_by_index:
                paragraph.paragraph_format.left_indent = Pt(indent_points_by_index[idx])
        doc.save(path)

    def _rewrite_document_xml(self, path: Path, rewrite) -> None:
        with ZipFile(path, "r") as zin:
            files = {info.filename: zin.read(info.filename) for info in zin.infolist()}
        root = ET.fromstring(files["word/document.xml"])
        rewrite(root)
        files["word/document.xml"] = ET.tostring(
            root,
            encoding="utf-8",
            xml_declaration=True,
        )
        with ZipFile(path, "w", compression=ZIP_DEFLATED) as zout:
            for name, data in files.items():
                zout.writestr(name, data)

    def test_removes_indented_paragraphs_and_blank_lines_left_by_removed_blocks(self) -> None:
        temp_dir = Path(tempfile.mkdtemp(prefix="subs_tools_clean_test_"))
        source_path = temp_dir / "input.docx"
        output_path = temp_dir / "output.docx"
        self._write_docx(
            source_path,
            [
                "字幕：",
                "00:00:01:00\t00:00:02:00\t第一句",
                "First translated line.",
                "",
                "https://example.com/source",
                "Indented source note A",
                "Indented source note B",
                "",
                "00:00:02:00\t00:00:03:00\t第二句",
                "Second translated line.",
            ],
            indented_indexes={4, 5, 6},
        )

        assert clean_subs is not None
        clean_subs.remove_sources_from_docx(source_path, output_path)

        texts = [p.text for p in Document(output_path).paragraphs]
        self.assertEqual(
            texts,
            [
                "字幕：",
                "00:00:01:00\t00:00:02:00\t第一句",
                "First translated line.",
                "00:00:02:00\t00:00:03:00\t第二句",
                "Second translated line.",
            ],
        )

    def test_preserves_non_indented_paragraphs(self) -> None:
        temp_dir = Path(tempfile.mkdtemp(prefix="subs_tools_clean_test_"))
        source_path = temp_dir / "input.docx"
        output_path = temp_dir / "output.docx"
        paragraphs = [
            "https://www.youtube.com/watch?v=top-header-link",
            "Top header title",
            "簡介：",
            "https://en.wikibooks.org/wiki/Traditional_Chinese_Medicine/Prescriptions",
            "*Five-Juice Drink*",
            "*五汁饮*",
            "Intro final line",
            "",
            "字幕：",
            "00:08:25:09\t00:08:28:02\t就是像我們中醫常常會有一個",
            "00:08:28:02\t00:08:29:00\t五汁飲",
            "https://health.businessweekly.com.tw/article/ARTL003018041",
            "Source note A",
            "Source note B",
            "",
            "XXX\t00:08:29:00\t00:08:43:11\t像梨子汁啊",
            "Juices made from pear and water chestnut.",
        ]
        self._write_docx(source_path, paragraphs)

        assert clean_subs is not None
        clean_subs.remove_sources_from_docx(source_path, output_path)

        texts = [p.text for p in Document(output_path).paragraphs]
        self.assertEqual(texts, paragraphs)

    def test_accepts_tracked_insertions_and_deletions_before_other_cleanup(self) -> None:
        temp_dir = Path(tempfile.mkdtemp(prefix="subs_tools_clean_test_"))
        source_path = temp_dir / "input.docx"
        output_path = temp_dir / "output.docx"
        self._write_docx(
            source_path,
            [
                "Keep",
                "Inserted line",
                "Deleted line",
            ],
        )

        def rewrite(root) -> None:
            paragraphs = root.findall(".//w:body/w:p", self.NS)

            inserted_paragraph = paragraphs[1]
            inserted_run = inserted_paragraph.find("w:r", self.NS)
            assert inserted_run is not None
            inserted_paragraph.remove(inserted_run)
            ins = ET.Element("{%s}ins" % self.NS["w"])
            ins.append(inserted_run)
            inserted_paragraph.append(ins)

            deleted_paragraph = paragraphs[2]
            deleted_run = deleted_paragraph.find("w:r", self.NS)
            assert deleted_run is not None
            deleted_text = "".join(
                node.text or "" for node in deleted_run.findall(".//w:t", self.NS)
            )
            deleted_paragraph.remove(deleted_run)
            deletion = ET.Element("{%s}del" % self.NS["w"])
            deleted_run = ET.Element("{%s}r" % self.NS["w"])
            deleted_text_node = ET.Element("{%s}delText" % self.NS["w"])
            deleted_text_node.text = deleted_text
            deleted_run.append(deleted_text_node)
            deletion.append(deleted_run)
            deleted_paragraph.append(deletion)

        self._rewrite_document_xml(source_path, rewrite)

        assert clean_subs is not None
        clean_subs.remove_sources_from_docx(source_path, output_path)

        texts = [p.text for p in Document(output_path).paragraphs if p.text.strip()]
        self.assertEqual(texts, ["Keep", "Inserted line"])
        with ZipFile(output_path) as zf:
            xml_root = ET.fromstring(zf.read("word/document.xml"))
        self.assertEqual(len(xml_root.findall(".//w:ins", self.NS)), 0)
        self.assertEqual(len(xml_root.findall(".//w:del", self.NS)), 0)
        self.assertEqual(len(xml_root.findall(".//w:moveFrom", self.NS)), 0)
        self.assertEqual(len(xml_root.findall(".//w:moveTo", self.NS)), 0)

    def test_accepts_inserted_indented_blocks_before_indent_cleanup(self) -> None:
        temp_dir = Path(tempfile.mkdtemp(prefix="subs_tools_clean_test_"))
        source_path = temp_dir / "input.docx"
        output_path = temp_dir / "output.docx"
        self._write_docx(
            source_path,
            [
                "字幕：",
                "00:00:01:00\t00:00:02:00\t第一句",
                "First translated line.",
                "",
                "Inserted source note",
                "",
                "00:00:02:00\t00:00:03:00\t第二句",
            ],
            indented_indexes={4},
        )

        def rewrite(root) -> None:
            paragraphs = root.findall(".//w:body/w:p", self.NS)
            inserted_paragraph = paragraphs[4]
            inserted_run = inserted_paragraph.find("w:r", self.NS)
            assert inserted_run is not None
            inserted_paragraph.remove(inserted_run)
            ins = ET.Element("{%s}ins" % self.NS["w"])
            ins.append(inserted_run)
            inserted_paragraph.append(ins)

        self._rewrite_document_xml(source_path, rewrite)

        assert clean_subs is not None
        clean_subs.remove_sources_from_docx(source_path, output_path)

        texts = [p.text for p in Document(output_path).paragraphs]
        self.assertEqual(
            texts,
            [
                "字幕：",
                "00:00:01:00\t00:00:02:00\t第一句",
                "First translated line.",
                "00:00:02:00\t00:00:03:00\t第二句",
            ],
        )

    def test_removes_indented_paragraphs_with_21_point_indent_variant(self) -> None:
        temp_dir = Path(tempfile.mkdtemp(prefix="subs_tools_clean_test_"))
        source_path = temp_dir / "input.docx"
        output_path = temp_dir / "output.docx"
        self._write_docx(
            source_path,
            [
                "字幕：",
                "00:00:01:00\t00:00:02:00\t第一句",
                "",
                "Shawn補充",
                "https://example.com/source",
                "補充內容",
                "",
                "00:00:02:00\t00:00:03:00\t第二句",
            ],
            indent_points_by_index={3: 21.3, 4: 21.3, 5: 21.3},
        )

        assert clean_subs is not None
        clean_subs.remove_sources_from_docx(source_path, output_path)

        texts = [p.text for p in Document(output_path).paragraphs]
        self.assertEqual(
            texts,
            [
                "字幕：",
                "00:00:01:00\t00:00:02:00\t第一句",
                "00:00:02:00\t00:00:03:00\t第二句",
            ],
        )

    def test_main_overwrites_input_by_default(self) -> None:
        temp_dir = Path(tempfile.mkdtemp(prefix="subs_tools_clean_test_"))
        source_path = temp_dir / "input.docx"
        self._write_docx(source_path, ["Line"])

        assert clean_subs is not None
        with mock.patch("sys.argv", ["clean_subs.py", str(source_path)]):
            clean_subs.main()

        self.assertTrue(source_path.exists())
        self.assertFalse((temp_dir / "input_nosource.docx").exists())

    def test_main_writes_copy_when_output_is_provided(self) -> None:
        temp_dir = Path(tempfile.mkdtemp(prefix="subs_tools_clean_test_"))
        source_path = temp_dir / "input.docx"
        output_path = temp_dir / "custom.docx"
        self._write_docx(source_path, ["Line"])

        assert clean_subs is not None
        with mock.patch(
            "sys.argv",
            ["clean_subs.py", str(source_path), "--output", str(output_path)],
        ):
            clean_subs.main()

        self.assertTrue(source_path.exists())
        self.assertTrue(output_path.exists())


if __name__ == "__main__":
    unittest.main()
