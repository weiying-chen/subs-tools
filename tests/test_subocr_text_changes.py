import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from subocr_to_txt import Cue, align_source_to_cues

class TextChangeTests(unittest.TestCase):
    def align(self, raw, source):
        return align_source_to_cues([Cue(0, 2, raw)], [source], max_source_lines_per_cue=4)[0]

    def test_added_character_at_each_position_requires_review(self):
        for text in ['啊我們回家', '我們啊回家', '我們回家啊']:
            with self.subTest(text=text), self.assertRaisesRegex(ValueError, '啊'):
                self.align('我們回家', text)

    def test_single_deleted_character_requires_review(self):
        with self.assertRaisesRegex(ValueError, '啊'):
            self.align('我們回家啊', '我們回家')

    def test_expanding_replacement_requires_review(self):
        with self.assertRaises(ValueError):
            self.align('我們回象', '我們回家啊')

    def test_correcting_glyph_and_restoring_spaces_is_allowed(self):
        self.assertEqual(self.align('團長我們回象', '團長 我們回家'), ['團長 我們回家'])

    def test_cli_rejects_unverified_correction_before_writing(self):
        script=Path(__file__).resolve().parents[1]/'subocr_to_txt.py'
        with tempfile.TemporaryDirectory() as tmp:
            p=Path(tmp)
            (p/'in.srt').write_text('1\n00:00:00,000 --> 00:00:02,000\n我們回家\n',encoding='utf-8')
            (p/'fix.tsv').write_text('00:01:00:00\t我們回家啊\n',encoding='utf-8')
            (p/'out.txt').write_bytes(b'Keep translation\r\n')
            (p/'out.baseline.txt').write_bytes(b'Keep baseline\r\n')
            result=subprocess.run([sys.executable,str(script),'--srt',str(p/'in.srt'),
                '--offset','00:01:00','--corrections',str(p/'fix.tsv'),
                '--out-baseline',str(p/'out.baseline.txt')],text=True,capture_output=True)
            self.assertNotEqual(result.returncode,0)
            self.assertIn('啊',result.stderr)
            self.assertIn('00:01:00:00',result.stderr)
            self.assertNotIn('Traceback',result.stderr)
            self.assertEqual((p/'out.txt').read_bytes(),b'Keep translation\r\n')
            self.assertEqual((p/'out.baseline.txt').read_bytes(),b'Keep baseline\r\n')
