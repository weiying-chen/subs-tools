import importlib.util
import unittest
from pathlib import Path
from unittest import mock


MODULE_PATH = Path('/home/weiying/python/subs-tools/crop_subs.py')
spec = importlib.util.spec_from_file_location('crop_subs', MODULE_PATH)
module = importlib.util.module_from_spec(spec)
assert spec and spec.loader
spec.loader.exec_module(module)


class CropSubsTest(unittest.TestCase):
    def test_missing_magick_message_includes_install_hint(self) -> None:
        message = module.missing_magick_message()
        self.assertIn('apt install -y imagemagick', message)

    def test_compute_center_crop_for_wide_image(self) -> None:
        crop = module.compute_center_crop(2000, 1000)
        self.assertEqual(crop, (1776, 999, 112, 0))

    def test_compute_center_crop_for_tall_image(self) -> None:
        crop = module.compute_center_crop(1000, 1000)
        self.assertEqual(crop, (992, 558, 4, 221))

    def test_compute_center_crop_for_exact_ratio(self) -> None:
        crop = module.compute_center_crop(1920, 1080)
        self.assertEqual(crop, (1920, 1080, 0, 0))

    def test_crop_dimensions_are_exact_16_by_9(self) -> None:
        crop_width, crop_height, _, _ = module.compute_center_crop(564, 318)
        self.assertEqual(crop_width * 9, crop_height * 16)

    def test_parse_args_defaults_to_overwrite(self) -> None:
        with mock.patch('sys.argv', ['crop_subs.py']):
            args = module.parse_args()
        self.assertTrue(args.overwrite)

    def test_parse_args_has_no_suffix_output_flag(self) -> None:
        with mock.patch('sys.argv', ['crop_subs.py', '--suffix-output']):
            with self.assertRaises(SystemExit):
                module.parse_args()


if __name__ == '__main__':
    unittest.main()
