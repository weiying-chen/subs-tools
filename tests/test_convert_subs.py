from __future__ import annotations

import tempfile
import unittest
from io import StringIO
from pathlib import Path
from unittest import mock

import convert_subs


class ConvertSubsTest(unittest.TestCase):
    def test_command_is_symlink_to_python_script(self) -> None:
        command_path = Path(__file__).resolve().parents[1] / "convert-subs"

        self.assertTrue(command_path.is_symlink())
        self.assertEqual(command_path.resolve(), command_path.with_name("convert_subs.py"))

    def test_resolve_input_paths_uses_current_directory_non_baseline_txt_when_empty(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            tmp_path = Path(tmp_dir)
            keep_a = tmp_path / "a.txt"
            keep_b = tmp_path / "b.txt"
            skip_baseline = tmp_path / "c.baseline.txt"
            skip_srt = tmp_path / "d.srt"
            keep_a.touch()
            keep_b.touch()
            skip_baseline.touch()
            skip_srt.touch()

            with mock.patch("convert_subs.Path.cwd", return_value=tmp_path):
                self.assertEqual(
                    convert_subs.resolve_input_paths([]),
                    [keep_a, keep_b],
                )

    def test_resolve_input_paths_keeps_explicit_files(self) -> None:
        self.assertEqual(
            convert_subs.resolve_input_paths(["one.txt", "two.txt"]),
            [Path("one.txt"), Path("two.txt")],
        )

    def test_build_srt_uses_body_section_and_english_line(self) -> None:
        text = "\n".join(
            [
                "HEADER:",
                "ignored",
                "BODY:",
                "00:00:00:00\t00:00:02:15\t中文字幕",
                "English subtitle #",
                "reference note",
                "",
            ]
        )

        self.assertEqual(
            convert_subs.build_srt(text, 30),
            "\n".join(
                [
                    "1",
                    "00:00:00,000 --> 00:00:02,500",
                    "English subtitle",
                    "",
                ]
            ),
        )

    def test_build_srt_ignores_xxx_marker_before_timestamp(self) -> None:
        text = "\n".join(
            [
                "BODY:",
                "XXX 00:02:40:00\t00:02:44:00\t補腎養陰 疏肝健脾",
                "(Cancer Prevention for a Yang-Deficient Constitution)",
            ]
        )

        self.assertEqual(
            convert_subs.build_srt(text, 30),
            "\n".join(
                [
                    "1",
                    "00:02:40,000 --> 00:02:44,000",
                    "(Cancer Prevention for a Yang-Deficient Constitution)",
                    "",
                ]
            ),
        )

    def test_build_srt_skips_xxx_without_timestamp(self) -> None:
        text = "\n".join(
            [
                "BODY:",
                "XXX chinese",
                "english",
            ]
        )

        self.assertEqual(convert_subs.build_srt(text, 30), "")

    def test_main_uses_default_output_path(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            source = Path(tmp_dir) / "sample.txt"
            source.write_text(
                "BODY:\n00:00:00:00\t00:00:01:00\t中文字幕\nEnglish line\n",
                encoding="utf-8",
            )

            exit_code = convert_subs.main([str(source)])

            self.assertEqual(exit_code, 0)
            output_path = source.with_suffix(".srt")
            self.assertTrue(output_path.exists())
            self.assertIn("English line", output_path.read_text(encoding="utf-8"))

    def test_main_uses_current_directory_when_no_paths_are_provided(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            tmp_path = Path(tmp_dir)
            source = tmp_path / "sample.txt"
            source.write_text(
                "BODY:\n00:00:00:00\t00:00:01:00\t中文字幕\nEnglish line\n",
                encoding="utf-8",
            )
            stdout = StringIO()

            with (
                mock.patch("convert_subs.Path.cwd", return_value=tmp_path),
                mock.patch("sys.stdout", stdout),
            ):
                exit_code = convert_subs.main([])

            self.assertEqual(exit_code, 0)
            self.assertTrue((tmp_path / "sample.srt").exists())
            self.assertIn("[written]", stdout.getvalue())


if __name__ == "__main__":
    unittest.main()
