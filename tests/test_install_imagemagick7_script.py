import unittest
from pathlib import Path


class InstallScriptTest(unittest.TestCase):
    def test_install_script_exists_with_required_steps(self) -> None:
        script = Path(__file__).resolve().parents[1] / 'install_imagemagick7.sh'
        self.assertTrue(script.exists())
        content = script.read_text(encoding='utf-8')
        self.assertIn('sudo apt install -y', content)
        self.assertIn('git clone --depth 1 https://github.com/ImageMagick/ImageMagick.git', content)
        self.assertIn('./configure --with-modules', content)
        self.assertIn('make -j"$(nproc)"', content)
        self.assertIn('sudo make install', content)
        self.assertIn('sudo ldconfig', content)


if __name__ == '__main__':
    unittest.main()
