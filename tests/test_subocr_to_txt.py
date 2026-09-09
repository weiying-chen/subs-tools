import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from subocr_to_txt import Cue, align_source_to_cues


class AlignmentTests(unittest.TestCase):
    def align(self, cues, source):
        return align_source_to_cues(cues, source, max_source_lines_per_cue=4)[0]

    def test_missing_source_segment_is_not_folded_into_next_cue(self):
        cues = [Cue(0, 1, '接下來介紹'), Cue(2, 4, '交通建設公共衛生')]
        with self.assertRaisesRegex(ValueError, '地方教育'):
            self.align(cues, ['接下來介紹', '地方教育', '交通建設', '公共衛生'])

    def test_missing_trailing_or_middle_line_requires_review(self):
        for source in (['交通建設', '公共衛生', '地方教育'],
                       ['交通建設', '地方教育', '公共衛生']):
            with self.subTest(source=source), self.assertRaisesRegex(ValueError, '地方教育'):
                self.align([Cue(0, 2, '交通建設公共衛生')], source)

    def test_supported_source_lines_can_still_share_one_cue(self):
        self.assertEqual(self.align([Cue(0, 2, '交通建設公共衛生')],
                                    ['交通建設', '公共衛生']), ['交通建設公共衛生'])

    def test_character_corrections_still_work(self):
        self.assertEqual(self.align([Cue(0, 2, '交通建投公共衛生')],
                                    ['交通建設', '公共衛生']), ['交通建設公共衛生'])

    def test_recovered_separate_cue_aligns_separately(self):
        source = ['接下來介紹', '地方教育', '交通建設公共衛生']
        cues = [Cue(0, 1, source[0]), Cue(1, 2, source[1]), Cue(2, 4, source[2])]
        self.assertEqual(self.align(cues, source), source)

    def test_source_slice_cannot_drop_ocr_prefix_even_with_number_correction(self):
        with self.assertRaisesRegex(ValueError, '接著我們'):
            self.align([Cue(0, 2, '接著我們在十八歲出發')], ['在18歲出發'])

    def test_source_cannot_drop_ocr_suffix_or_middle_phrase(self):
        for ocr in ('大家一起出發然後回家', '大家然後回家一起出發'):
            with self.subTest(ocr=ocr), self.assertRaisesRegex(ValueError, '然後回家'):
                self.align([Cue(0, 2, ocr)], ['大家一起出發'])

    def test_punctuation_and_known_ocr_noise_can_be_cleaned(self):
        self.assertEqual(self.align([Cue(0, 2, '，大家一起出發SPIRIT')],
                                    ['大家一起出發']), ['大家一起出發'])

    def test_cli_rejects_stale_correction_without_touching_translations(self):
        script = Path(__file__).resolve().parents[1] / 'subocr_to_txt.py'
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            srt = root / 'in.srt'
            srt.write_text('1\n00:00:00,000 --> 00:00:02,000\n接著我們一起出發\n', encoding='utf-8')
            corrections = root / 'corrections.tsv'
            corrections.write_text('00:01:00:00\t一起出發\n', encoding='utf-8')
            baseline, translated = root / 'out.baseline.txt', root / 'out.txt'
            baseline.write_bytes(b'original baseline\n')
            translated.write_bytes(b'Existing translation\n')
            result = subprocess.run([sys.executable, str(script), '--srt', str(srt),
                                     '--offset', '00:01:00', '--corrections', str(corrections),
                                     '--out-baseline', str(baseline)], capture_output=True, text=True)
            self.assertNotEqual(result.returncode, 0)
            self.assertIn('接著我們', result.stderr)
            self.assertIn('00:01:00:00', result.stderr)
            self.assertNotIn('Traceback', result.stderr)
            self.assertEqual(baseline.read_bytes(), b'original baseline\n')
            self.assertEqual(translated.read_bytes(), b'Existing translation\n')

    def test_cli_reports_absolute_gap_and_preserves_existing_outputs(self):
        script = Path(__file__).resolve().parents[1] / 'subocr_to_txt.py'
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            srt = root / 'in.srt'
            srt.write_text('1\n00:00:00,000 --> 00:00:01,000\n接下來介紹\n\n'
                           '2\n00:00:02,000 --> 00:00:04,000\n交通建設公共衛生\n', encoding='utf-8')
            source = root / 'source.txt'
            source.write_text('接下來介紹\n地方教育\n交通建設\n公共衛生\n', encoding='utf-8')
            baseline, translated = root / 'out.baseline.txt', root / 'out.txt'
            baseline.write_bytes(b'original baseline\r\n')
            translated.write_bytes(b'Keep this English translation.\r\n')
            result = subprocess.run([sys.executable, str(script), '--srt', str(srt),
                                     '--offset', '00:01:00', '--source', str(source),
                                     '--out-baseline', str(baseline)], capture_output=True, text=True)
            self.assertNotEqual(result.returncode, 0)
            self.assertIn('地方教育', result.stderr)
            self.assertIn('00:01:01:00', result.stderr)
            self.assertIn('00:01:02:00', result.stderr)
            self.assertNotIn('Traceback', result.stderr)
            self.assertEqual(baseline.read_bytes(), b'original baseline\r\n')
            self.assertEqual(translated.read_bytes(), b'Keep this English translation.\r\n')


if __name__ == '__main__':
    unittest.main()
