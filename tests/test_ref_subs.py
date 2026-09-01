import importlib.util
import sys
import tempfile
import unittest
from pathlib import Path

from docx import Document


MODULE_PATH = Path(__file__).resolve().parents[1] / "ref_subs.py"


def load_module(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    assert spec and spec.loader
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


ref_module = load_module("ref_subs", MODULE_PATH)


def write_subtitle_docx(path: Path, title: str, english: str) -> None:
    document = Document()
    for text in [
        "建議YT標題：",
        title,
        "建議標題：",
        title.split(" (")[0],
        "簡介：",
        "English introduction.",
        "中文簡介。",
        "選圖：",
        "字幕：",
        "00:00:01:00\t00:00:02:00\t中文",
        english,
    ]:
        document.add_paragraph(text)
    document.save(path)


class RefSubsTest(unittest.TestCase):
    def test_complete_output_and_edited_pairs_are_discovered(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            source = Path(tmpdir)
            (source / "output").mkdir()
            (source / "edited").mkdir()
            for index in range(1, 4):
                (source / "output" / f"episode {index}_al.docx").touch()
                (source / "edited" / f"episode {index}_final.docx").touch()
            (source / "output" / "unfinished_al.docx").touch()

            pairs = ref_module.discover_pairs(source)

            self.assertEqual([pair.key for pair in pairs], ["episode 1", "episode 2", "episode 3"])

    def test_docx_is_normalized_to_standard_txt_fields(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            path = Path(tmpdir) / "sample.docx"
            write_subtitle_docx(path, "English Title (中文標題)", "English subtitle.")

            rendered = ref_module.docx_to_txt(path)

            self.assertIn("YT_TITLE_SUGGESTED: English Title (中文標題)", rendered)
            self.assertIn("TITLE_SUGGESTED: English Title", rendered)
            self.assertIn("INTRO:\n\nEnglish introduction.\n\n中文簡介。", rendered)
            self.assertIn("THUMBNAIL: English Title.png", rendered)
            self.assertIn("BODY:\n\n00:00:01:00\t00:00:02:00\t中文\nEnglish subtitle.", rendered)

    def test_latest_four_selects_folders_and_keeps_every_pair(self) -> None:
        batches = [
            (Path(f"ev{index}"), [
                ref_module.Pair(
                    f"episode {index} [{part}]",
                    Path(f"pre-{index}-{part}"),
                    Path(f"post-{index}-{part}"),
                )
                for part in range(1, index + 1)
            ])
            for index in range(1, 6)
        ]

        selected = ref_module.latest_batches(batches)

        self.assertEqual([folder.name for folder, _ in selected], ["ev2", "ev3", "ev4", "ev5"])
        self.assertEqual([len(pairs) for _, pairs in selected], [2, 3, 4, 5])

    def test_pairs_are_collected_and_filtered_across_multiple_folders(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            sources = [root / "em4", root / "em6"]
            names = [
                "大愛真健康 episode 20260101",
                "大愛真健康 episode 20260201",
            ]
            for source, name in zip(sources, names):
                (source / "output").mkdir(parents=True)
                (source / "edited").mkdir()
                (source / "output" / f"{name}_al.docx").touch()
                (source / "edited" / f"{name}_final.docx").touch()
                (source / "output" / "別的節目_al.docx").touch()
                (source / "edited" / "別的節目_final.docx").touch()

            pairs = ref_module.discover_pairs(sources, series="大愛真健康")

            self.assertEqual([pair.key for pair in pairs], names)

    def test_batch_folders_are_discovered_below_subtitle_root(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            valid = [root / "em4", root / "em6"]
            for source in valid:
                (source / "output").mkdir(parents=True)
                (source / "edited").mkdir()
            (root / "refs").mkdir()
            (root / "incomplete" / "output").mkdir(parents=True)

            self.assertEqual(ref_module.discover_sources(root), valid)

    def test_partially_edited_folder_is_not_a_complete_batch(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            source = Path(tmpdir) / "ev30"
            (source / "output").mkdir(parents=True)
            (source / "edited").mkdir()
            for index in range(1, 3):
                (source / "output" / f"人文講堂 episode [{index}]_al.docx").touch()
            (source / "edited" / "人文講堂 episode [1]_final.docx").touch()

            self.assertEqual(ref_module.discover_batches([source], "人文講堂"), [])


if __name__ == "__main__":
    unittest.main()
