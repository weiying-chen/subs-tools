import tempfile
import unittest
from pathlib import Path
from unittest import mock

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
    def _write_docx(
        self,
        path: Path,
        paragraphs: list[str],
        *,
        indented_indexes: set[int] | None = None,
    ) -> None:
        doc = Document()
        indented_indexes = indented_indexes or set()
        for idx, text in enumerate(paragraphs):
            paragraph = doc.add_paragraph(text)
            if idx in indented_indexes:
                paragraph.paragraph_format.left_indent = Pt(24)
        doc.save(path)

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
