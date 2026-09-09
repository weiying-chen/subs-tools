import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

import subocr_to_txt as converter
from subocr_to_txt import Cue


class DuplicateCueTests(unittest.TestCase):
    def test_continuous_duplicates_keep_full_interval_and_text(self):
        cues = [Cue(1, 1.5, '我們 一起出發'), Cue(1.5, 3, '我們 一起出發'),
                Cue(3, 3.5, '我們 一起出發'), Cue(3.5, 4, '我們 一起出發')]
        before = list(cues)
        self.assertEqual(converter.merge_duplicate_cues(cues), [Cue(1, 4, '我們 一起出發')])
        self.assertEqual(cues, before)

    def test_repetition_after_gap_or_another_subtitle_is_preserved(self):
        cues = [Cue(0, 1, '大家好'), Cue(1.5, 2, '大家好'),
                Cue(2, 3, '請坐'), Cue(3, 4, '大家好')]
        self.assertEqual(converter.merge_duplicate_cues(cues), cues)

    def test_overlap_different_spacing_and_punctuation_are_not_collapsed(self):
        for cues in ([Cue(0, 2, '大家好'), Cue(1, 3, '大家好')],
                     [Cue(0, 1, '大家好'), Cue(1, 2, '大家好？')],
                     [Cue(0, 1, '大家 好'), Cue(1, 2, '大家好')]):
            with self.subTest(cues=cues):
                self.assertEqual(converter.merge_duplicate_cues(cues), cues)

    def test_empty_and_single_cue(self):
        self.assertEqual(converter.merge_duplicate_cues([]), [])
        cues = [Cue(0, 1, '大家好')]
        self.assertEqual(converter.merge_duplicate_cues(cues), cues)

    def test_annotated_boundary_is_preserved(self):
        cues = [Cue(0, 1, '大家好'), Cue(1, 2, '大家好')]
        self.assertEqual(converter.merge_duplicate_cues(cues, preserve_starts={1}), cues)

    def run_conversion(self, root, *, layout=None):
        script = Path(__file__).resolve().parents[1] / 'subocr_to_txt.py'
        srt = root / 'input.srt'
        srt.write_text('1\n00:00:00,000 --> 00:00:00,500\n跟大家一起分亨\n\n'
                       '2\n00:00:00,500 --> 00:00:02,000\n跟大家一起分享\n\n'
                       '3\n00:00:02,000 --> 00:00:03,000\n今天的故事\n', encoding='utf-8')
        corrections = root / 'corrections.tsv'
        corrections.write_text('00:01:00:00\t跟大家一起分享\n', encoding='utf-8')
        baseline = root / 'out.baseline.txt'
        args = [sys.executable, str(script), '--srt', str(srt), '--offset', '00:01:00',
                '--corrections', str(corrections), '--out-baseline', str(baseline)]
        if layout is not None:
            path = root / 'layout.txt'
            path.write_text(layout, encoding='utf-8')
            args += ['--blank-lines-from', str(path)]
        result = subprocess.run(args, capture_output=True, text=True)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(baseline.read_bytes(), (root / 'out.txt').read_bytes())
        return baseline.read_text(), result.stdout

    def test_cli_merges_after_corrections_in_both_outputs(self):
        with tempfile.TemporaryDirectory() as tmp:
            content, stdout = self.run_conversion(Path(tmp))
            self.assertEqual(content, '00:01:00:00\t00:01:02:00\t跟大家一起分享\n'
                                      '00:01:02:00\t00:01:03:00\t今天的故事\n')
            self.assertIn('merged 1', stdout)

    def test_cli_retains_notes_at_internal_duplicate_boundary(self):
        layout = ('00:01:00:00\t00:01:00:15\t跟大家一起分享\n'
                  'Keep this note.\n\n'
                  '00:01:00:15\t00:01:02:00\t跟大家一起分享\n')
        with tempfile.TemporaryDirectory() as tmp:
            content, _ = self.run_conversion(Path(tmp), layout=layout)
            self.assertIn('Keep this note.\n\n00:01:00:15', content)
            self.assertEqual(content.count('跟大家一起分享'), 2)


if __name__ == '__main__':
    unittest.main()
