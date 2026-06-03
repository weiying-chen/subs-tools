import os
import stat
import subprocess
import tempfile
import unittest
from pathlib import Path


SCRIPT_PATH = Path(__file__).resolve().parents[1] / 'gen_subs.sh'


class GenSubsScriptTest(unittest.TestCase):
    def test_runs_crop_and_prints_crop_section(self) -> None:
        temp_dir = Path(tempfile.mkdtemp(prefix='subs_tools_gen_test_'))
        target_dir = temp_dir / 'target'
        target_dir.mkdir(parents=True, exist_ok=True)

        (target_dir / 'sample.txt').write_text(
            'YT_TITLE_SUGGESTED:\n\nTITLE_SUGGESTED:\n\nINTRO:\n\nTHUMBNAIL:\n\nBODY:\n\n',
            encoding='utf-8',
        )
        (target_dir / 'sample.docx').write_text('dummy', encoding='utf-8')
        (target_dir / 'thumb.png').write_text('png', encoding='utf-8')

        template_path = temp_dir / 'template.docx'
        template_path.write_text('template', encoding='utf-8')

        generate_script = temp_dir / 'fake_generate_subs.py'
        generate_script.write_text(
            '#!/usr/bin/env python3\n'
            'import sys\n'
            'sys.exit(0)\n',
            encoding='utf-8',
        )
        generate_script.chmod(generate_script.stat().st_mode | stat.S_IXUSR)

        crop_script = temp_dir / 'fake_crop_subs.py'
        crop_script.write_text(
            '#!/usr/bin/env python3\n'
            'print("[wrote] fake-cropped.png")\n',
            encoding='utf-8',
        )
        crop_script.chmod(crop_script.stat().st_mode | stat.S_IXUSR)

        env = dict(os.environ)
        env.update(
            {
                'GENERATE_SUBS_SCRIPT': str(generate_script),
                'GENERATE_SUBS_PYTHON': '/usr/bin/python3',
                'GENERATE_SUBS_TEMPLATE': str(template_path),
                'GENERATE_SUBS_CROP_SCRIPT': str(crop_script),
            }
        )
        result = subprocess.run(
            [str(SCRIPT_PATH), str(target_dir)],
            check=True,
            capture_output=True,
            text=True,
            env=env,
        )

        self.assertIn('[created] sample_al.docx', result.stdout)
        self.assertIn('[crop] fake-cropped.png', result.stdout)
        self.assertNotIn('[crop] start', result.stdout)
        self.assertIn(
            '[done] generated: 1, skipped: 0, copied png: 0, failed: 0, crop_failed: 0',
            result.stdout,
        )

    def test_copies_thumbnail_after_crop(self) -> None:
        temp_dir = Path(tempfile.mkdtemp(prefix='subs_tools_gen_test_'))
        target_dir = temp_dir / 'target'
        target_dir.mkdir(parents=True, exist_ok=True)

        (target_dir / 'sample.txt').write_text(
            'YT_TITLE_SUGGESTED:\n\nTITLE_SUGGESTED:\n\nINTRO:\n\nTHUMBNAIL: thumb.png\n\nBODY:\n\n',
            encoding='utf-8',
        )
        (target_dir / 'sample.docx').write_text('dummy', encoding='utf-8')
        (target_dir / 'thumb.png').write_text('before-crop', encoding='utf-8')

        template_path = temp_dir / 'template.docx'
        template_path.write_text('template', encoding='utf-8')

        generate_script = temp_dir / 'fake_generate_subs.py'
        generate_script.write_text(
            '#!/usr/bin/env python3\n'
            'import sys\n'
            'sys.exit(0)\n',
            encoding='utf-8',
        )
        generate_script.chmod(generate_script.stat().st_mode | stat.S_IXUSR)

        crop_script = temp_dir / 'fake_crop_subs.py'
        crop_script.write_text(
            '#!/usr/bin/env python3\n'
            'from pathlib import Path\n'
            'import sys\n'
            'target = Path(sys.argv[1])\n'
            '(target / "thumb.png").write_text("after-crop", encoding="utf-8")\n'
            'print("[wrote] thumb.png")\n',
            encoding='utf-8',
        )
        crop_script.chmod(crop_script.stat().st_mode | stat.S_IXUSR)

        env = dict(os.environ)
        env.update(
            {
                'GENERATE_SUBS_SCRIPT': str(generate_script),
                'GENERATE_SUBS_PYTHON': '/usr/bin/python3',
                'GENERATE_SUBS_TEMPLATE': str(template_path),
                'GENERATE_SUBS_CROP_SCRIPT': str(crop_script),
            }
        )
        subprocess.run(
            [str(SCRIPT_PATH), str(target_dir)],
            check=True,
            capture_output=True,
            text=True,
            env=env,
        )

        copied_thumb = target_dir / 'output' / 'thumb.png'
        self.assertTrue(copied_thumb.exists())
        self.assertEqual(copied_thumb.read_text(encoding='utf-8'), 'after-crop')

    def test_thumbnail_parser_ignores_trailing_star_marker(self) -> None:
        temp_dir = Path(tempfile.mkdtemp(prefix='subs_tools_gen_test_'))
        target_dir = temp_dir / 'target'
        target_dir.mkdir(parents=True, exist_ok=True)

        (target_dir / 'sample.txt').write_text(
            'YT_TITLE_SUGGESTED:\n\nTITLE_SUGGESTED:\n\nINTRO:\n\nTHUMBNAIL: thumb.png *\n\nBODY:\n\n',
            encoding='utf-8',
        )
        (target_dir / 'sample.docx').write_text('dummy', encoding='utf-8')
        (target_dir / 'thumb.png').write_text('thumb-content', encoding='utf-8')

        template_path = temp_dir / 'template.docx'
        template_path.write_text('template', encoding='utf-8')

        generate_script = temp_dir / 'fake_generate_subs.py'
        generate_script.write_text(
            '#!/usr/bin/env python3\n'
            'import sys\n'
            'sys.exit(0)\n',
            encoding='utf-8',
        )
        generate_script.chmod(generate_script.stat().st_mode | stat.S_IXUSR)

        crop_script = temp_dir / 'fake_crop_subs.py'
        crop_script.write_text(
            '#!/usr/bin/env python3\n'
            'print("[wrote] thumb.png")\n',
            encoding='utf-8',
        )
        crop_script.chmod(crop_script.stat().st_mode | stat.S_IXUSR)

        env = dict(os.environ)
        env.update(
            {
                'GENERATE_SUBS_SCRIPT': str(generate_script),
                'GENERATE_SUBS_PYTHON': '/usr/bin/python3',
                'GENERATE_SUBS_TEMPLATE': str(template_path),
                'GENERATE_SUBS_CROP_SCRIPT': str(crop_script),
            }
        )
        result = subprocess.run(
            [str(SCRIPT_PATH), str(target_dir)],
            check=True,
            capture_output=True,
            text=True,
            env=env,
        )

        self.assertIn('[copied] thumb.png', result.stdout)
        self.assertTrue((target_dir / 'output' / 'thumb.png').exists())


if __name__ == '__main__':
    unittest.main()
