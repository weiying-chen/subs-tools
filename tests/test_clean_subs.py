import tempfile
import unittest
from pathlib import Path

try:
    from docx import Document
except ModuleNotFoundError:
    Document = None
    clean_subs = None
else:
    import clean_subs


@unittest.skipIf(Document is None, "python-docx is not installed")
class CleanSubsTest(unittest.TestCase):
    def _write_docx(self, path: Path, paragraphs: list[str]) -> None:
        doc = Document()
        for text in paragraphs:
            doc.add_paragraph(text)
        doc.save(path)

    def test_remove_sources_blocks_only_in_intro_and_subs_sections(self) -> None:
        temp_dir = Path(tempfile.mkdtemp(prefix="subs_tools_clean_test_"))
        source_path = temp_dir / "input.docx"
        output_path = temp_dir / "output.docx"
        self._write_docx(
            source_path,
            [
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
            ],
        )

        assert clean_subs is not None
        clean_subs.remove_sources_from_docx(source_path, output_path)

        texts = [p.text for p in Document(output_path).paragraphs]
        self.assertIn("https://www.youtube.com/watch?v=top-header-link", texts)
        self.assertNotIn(
            "https://en.wikibooks.org/wiki/Traditional_Chinese_Medicine/Prescriptions",
            texts,
        )
        self.assertNotIn("https://health.businessweekly.com.tw/article/ARTL003018041", texts)
        self.assertNotIn("*Five-Juice Drink*", texts)
        self.assertNotIn("*五汁饮*", texts)
        self.assertNotIn("Source note A", texts)
        self.assertNotIn("Source note B", texts)
        self.assertNotIn("Intro final line", texts)
        self.assertIn("XXX\t00:08:29:00\t00:08:43:11\t像梨子汁啊", texts)
        self.assertIn("Juices made from pear and water chestnut.", texts)

    def test_remove_blank_lines_between_subtitle_timestamps(self) -> None:
        temp_dir = Path(tempfile.mkdtemp(prefix="subs_tools_clean_test_"))
        source_path = temp_dir / "input.docx"
        output_path = temp_dir / "output.docx"
        self._write_docx(
            source_path,
            [
                "字幕：",
                "00:00:01:00\t00:00:02:00\t第一句",
                "",
                "00:00:02:00\t00:00:03:00\t第二句",
                "",
                "Normal line",
            ],
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
                "",
                "Normal line",
            ],
        )


if __name__ == "__main__":
    unittest.main()
