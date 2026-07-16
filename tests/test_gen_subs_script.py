from pathlib import Path
import unittest


class GenSubsScriptTest(unittest.TestCase):
    def test_gen_subs_does_not_run_image_passes(self) -> None:
        script = (Path(__file__).resolve().parents[1] / "gen_subs.sh").read_text(
            encoding="utf-8"
        )

        self.assertNotIn("GENERATE_SUBS_CROP_SCRIPT", script)
        self.assertNotIn("CROP_SCRIPT_PATH", script)
        self.assertNotIn("THUMBNAIL:", script)
        self.assertNotIn("thumbnails_to_copy", script)
        self.assertNotIn("copied png", script)
        self.assertNotIn("crop_failed", script)


if __name__ == "__main__":
    unittest.main()
