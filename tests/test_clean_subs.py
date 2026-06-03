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

    def test_preserves_existing_paragraphs_without_cleanup_rules(self) -> None:
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
        self._write_docx(
            source_path,
            paragraphs,
        )

        assert clean_subs is not None
        clean_subs.remove_sources_from_docx(source_path, output_path)

        texts = [p.text for p in Document(output_path).paragraphs]
        self.assertEqual(texts, paragraphs)


if __name__ == "__main__":
    unittest.main()
