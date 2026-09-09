import unittest
from subocr_to_txt import Cue, align_source_to_cues


class AlignmentTests(unittest.TestCase):
    def align(self, cues, source):
        return align_source_to_cues(cues, source, max_source_lines_per_cue=4)[0]

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

