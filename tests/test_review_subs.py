import importlib.util
import sys
import tempfile
import unittest
from pathlib import Path


MODULE_PATH = Path(__file__).resolve().parents[1] / "review_subs.py"


def load_module(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    assert spec and spec.loader
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


review_module = load_module("review_subs", MODULE_PATH)


class ReviewSubsTest(unittest.TestCase):
    def test_prepares_only_missing_srt_files_from_matching_txt_files(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            directory = Path(tmpdir)
            missing_source = directory / "episode-one.txt"
            missing_source.write_text(
                "BODY:\n"
                "00:00:01:00\t00:00:02:00\t中文\n"
                "English line.\n",
                encoding="utf-8",
            )
            existing_source = directory / "episode-two.txt"
            existing_source.write_text("BODY:\n", encoding="utf-8")
            existing_subtitle = directory / "episode-two.srt"
            existing_subtitle.write_text("manually edited\n", encoding="utf-8")
            (directory / "episode-one.baseline.txt").write_text(
                "BODY:\n", encoding="utf-8"
            )

            generated = review_module.prepare_subtitle_files(directory)

            self.assertEqual(generated, [directory / "episode-one.srt"])
            self.assertIn(
                "00:00:01,000 --> 00:00:02,000",
                generated[0].read_text(encoding="utf-8"),
            )
            self.assertEqual(
                existing_subtitle.read_text(encoding="utf-8"),
                "manually edited\n",
            )
            self.assertFalse((directory / "episode-one.baseline.srt").exists())

    def test_matching_stem_is_preferred_among_multiple_videos(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            directory = Path(tmpdir)
            subtitle = directory / "episode.srt"
            matching_video = directory / "episode.mp4"
            subtitle.touch()
            matching_video.touch()
            (directory / "other.webm").touch()

            self.assertEqual(
                review_module.discover_media(directory),
                (matching_video, [subtitle]),
            )

    def test_one_video_and_one_subtitle_can_have_different_stems(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            directory = Path(tmpdir)
            video = directory / "video.mp4"
            subtitle = directory / "subtitles.srt"
            video.touch()
            subtitle.touch()

            self.assertEqual(
                review_module.discover_media(directory),
                (video, [subtitle]),
            )

    def test_conventional_pair_is_preferred_over_extra_video(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            directory = Path(tmpdir)
            video = directory / "video.mp4"
            subtitle = directory / "subtitles.srt"
            video.touch()
            subtitle.touch()
            (directory / "downloaded-title.mp4").touch()

            self.assertEqual(
                review_module.discover_media(directory),
                (video, [subtitle]),
            )

    def test_mpv_command_applies_subtitle_background_and_larger_font(self) -> None:
        command = review_module.build_mpv_command(
            mpv="mpv",
            video=Path("/story/episode.mp4"),
            subtitle=Path("/story/episode.srt"),
            chapters=Path("/cache/chapters.ffmetadata"),
            input_config=Path("/cache/input.conf"),
        )

        self.assertEqual(command[0], "mpv")
        self.assertIn("--sub-file=/story/episode.srt", command)
        self.assertIn("--sub-font-size=48", command)
        self.assertIn("--sub-border-style=background-box", command)
        self.assertIn("--sub-back-color=#C0000000", command)
        self.assertIn("--chapters-file=/cache/chapters.ffmetadata", command)
        self.assertIn("--input-conf=/cache/input.conf", command)
        self.assertEqual(command[-1], "/story/episode.mp4")

    def test_multiple_srt_files_are_sorted_and_renumbered(self) -> None:
        first = """1
00:00:05,000 --> 00:00:06,000
Second cue
"""
        second = """7
00:00:01,000 --> 00:00:02,000
First cue
"""

        self.assertEqual(
            review_module.merge_srt_contents([first, second]),
            """1
00:00:01,000 --> 00:00:02,000
First cue

2
00:00:05,000 --> 00:00:06,000
Second cue
""",
        )

    def test_srt_sources_become_player_chapters(self) -> None:
        sources = [
            (
                Path("part-two.srt"),
                "1\n00:00:05,000 --> 00:00:08,000\nSecond\n",
            ),
            (
                Path("part-one.srt"),
                "1\n00:00:01,000 --> 00:00:03,000\nFirst\n",
            ),
        ]

        chapters = review_module.render_chapters(sources)

        self.assertIn("START=1000\nEND=5000\ntitle=part-one.srt", chapters)
        self.assertIn("START=5000\nEND=8000\ntitle=part-two.srt", chapters)


if __name__ == "__main__":
    unittest.main()
