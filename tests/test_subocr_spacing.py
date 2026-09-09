import unittest
from PIL import Image, ImageDraw
from subocr_spacing import suggest_spacing, export_corrections

class SpacingTests(unittest.TestCase):
    def test_gap_between_characters(self):
        image = Image.new('L', (150, 35))
        draw = ImageDraw.Draw(image)
        for x in (10, 35, 75, 100):
            draw.rectangle((x, 5, x + 19, 30), fill=255)
        result = suggest_spacing(image, '甲乙丙丁')
        self.assertEqual(result['suggested'], '甲乙 丙丁')

    def test_mismatched_glyph_count_needs_review(self):
        image = Image.new('L', (100, 35))
        ImageDraw.Draw(image).rectangle((10, 5, 30, 30), fill=255)
        self.assertIsNone(suggest_spacing(image, '甲乙')['suggested'])

    def test_export_only_approved_spacing_changes(self):
        rows = [dict(start='00:00:01:00', current='甲乙', suggested='甲 乙', approved=False)]
        self.assertEqual(export_corrections(rows), '')
        rows[0]['approved'] = True
        self.assertEqual(export_corrections(rows), '00:00:01:00\t甲 乙\n')
        rows[0]['suggested'] = '甲丙'
        with self.assertRaises(ValueError):
            export_corrections(rows)

if __name__ == '__main__':
    unittest.main()
