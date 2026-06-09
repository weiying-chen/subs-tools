from pathlib import Path
import tempfile
import unittest
from unittest import mock

import clean_subs


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


if __name__ == "__main__":
    unittest.main()
