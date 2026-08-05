import importlib.util
import sys
import unittest
from pathlib import Path


SETUP_MODULE_PATH = Path(__file__).resolve().parents[1] / "setup_subs.py"


def load_module(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    assert spec and spec.loader
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


setup_module = load_module("setup_subs", SETUP_MODULE_PATH)


class SetupSubsYoutubeTest(unittest.TestCase):
    def test_youtube_download_command_targets_docx_directory(self) -> None:
        command = setup_module.build_youtube_download_command(
            "https://www.youtube.com/watch?v=tCL86SwAlFI",
            Path("/work/subs"),
        )

        self.assertEqual(
            command,
            [
                "yt-dlp",
                "--no-playlist",
                "--paths",
                "/work/subs",
                "https://www.youtube.com/watch?v=tCL86SwAlFI",
            ],
        )

    def test_first_url_is_found_in_docx_text(self) -> None:
        root = setup_module.ET.fromstring(
            f"""
            <w:document xmlns:w="{setup_module.W_NS}">
              <w:body><w:p><w:r><w:t>
                Source: https://youtu.be/tCL86SwAlFI
              </w:t></w:r></w:p></w:body>
            </w:document>
            """
        )

        self.assertEqual(
            setup_module.find_first_url_in_root(root),
            "https://youtu.be/tCL86SwAlFI",
        )


if __name__ == "__main__":
    unittest.main()
