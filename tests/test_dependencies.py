from pathlib import Path
import unittest


class DependencyTest(unittest.TestCase):
    def test_runtime_dependencies_are_declared(self) -> None:
        requirements = (
            Path(__file__).resolve().parents[1] / "requirements.txt"
        ).read_text(encoding="utf-8").lower().splitlines()

        self.assertEqual(
            {line.strip() for line in requirements if line.strip()},
            {"pillow", "python-docx", "rapidfuzz"},
        )


if __name__ == "__main__":
    unittest.main()
