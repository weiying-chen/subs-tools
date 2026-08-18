import importlib.util
import sys
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest import mock


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
        with mock.patch.object(
            setup_module.Path,
            "home",
            return_value=Path("/home/tester"),
        ):
            command = setup_module.build_youtube_download_command(
                "https://www.youtube.com/watch?v=tCL86SwAlFI",
                Path("/work/subs"),
            )

        self.assertEqual(
            command,
            [
                "yt-dlp",
                "--no-playlist",
                "--js-runtimes",
                "node",
                "--extractor-args",
                "youtubepot-bgutilscript:script_path=/home/tester/.local/share/bgutil-ytdlp-pot-provider/server/build/generate_once.js",
                "--extractor-args",
                "youtube:player_client=mweb",
                "--paths",
                "/work/subs",
                "https://www.youtube.com/watch?v=tCL86SwAlFI",
            ],
        )

    def test_youtube_download_retries_with_combined_format(self) -> None:
        failure = setup_module.subprocess.CalledProcessError(1, ["yt-dlp"])

        with (
            mock.patch.object(setup_module.shutil, "which", return_value="/usr/bin/yt-dlp"),
            mock.patch.object(
                setup_module.subprocess,
                "run",
                side_effect=[failure, mock.DEFAULT],
            ) as run,
        ):
            setup_module.download_youtube_video(
                "https://www.youtube.com/watch?v=tCL86SwAlFI",
                Path("/work/subs"),
            )

        self.assertEqual(run.call_count, 2)
        first_command = run.call_args_list[0].args[0]
        fallback_command = run.call_args_list[1].args[0]
        self.assertNotIn("--format", first_command)
        self.assertEqual(
            fallback_command[fallback_command.index("--format") + 1],
            "18",
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

    def test_tcmaster_page_is_downloaded_directly(self) -> None:
        source_url = "https://tcmaster.daai.tv/2019/07/30/example/"

        with mock.patch.object(setup_module.urllib.request, "urlopen") as urlopen:
            self.assertEqual(
                setup_module.resolve_youtube_url(source_url),
                source_url,
            )
        urlopen.assert_not_called()

    def test_duplicate_video_url_is_downloaded_once_per_run(self) -> None:
        youtube_url = "https://www.youtube.com/watch?v=tCL86SwAlFI"
        with tempfile.TemporaryDirectory() as tmpdir:
            docx_paths = [Path(tmpdir) / "one.docx", Path(tmpdir) / "two.docx"]
            for path in docx_paths:
                path.touch()

            args = SimpleNamespace(paths=docx_paths, mode="auto", out="both", force=False)
            with (
                mock.patch.object(setup_module, "parse_args", return_value=args),
                mock.patch.object(setup_module, "extract_ts_lines", return_value=[]),
                mock.patch.object(
                    setup_module, "find_first_docx_url", return_value=youtube_url
                ),
                mock.patch.object(
                    setup_module, "resolve_youtube_url", return_value=youtube_url
                ),
                mock.patch.object(setup_module, "copy_to_clipboard", return_value=True),
                mock.patch.object(setup_module, "download_youtube_video") as download,
            ):
                self.assertEqual(setup_module.main(), 0)

        download.assert_called_once_with(youtube_url, docx_paths[0].parent)


if __name__ == "__main__":
    unittest.main()
