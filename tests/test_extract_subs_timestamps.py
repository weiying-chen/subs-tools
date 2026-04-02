import importlib.util
import os
import subprocess
import tempfile
import unittest
import zipfile
from pathlib import Path


MODULE_PATH = Path('/home/weiying/python/subs-tools/extract_subs_timestamps.py')
spec = importlib.util.spec_from_file_location('extract_subs_timestamps', MODULE_PATH)
module = importlib.util.module_from_spec(spec)
assert spec and spec.loader
spec.loader.exec_module(module)


class ExtractSubsTimestampsTest(unittest.TestCase):
    def _make_docx(self, xml: str) -> Path:
        temp_dir = Path(tempfile.mkdtemp(prefix='subs_tools_test_'))
        docx_path = temp_dir / 'sample.docx'
        with zipfile.ZipFile(docx_path, 'w', compression=zipfile.ZIP_DEFLATED) as zf:
            zf.writestr('word/document.xml', xml)
        return docx_path

    def test_auto_falls_back_to_all_paragraphs(self) -> None:
        xml = '''<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main">
  <w:body>
    <w:p><w:r><w:t>00:00:06:28\t00:00:08:11\t大愛真健康</w:t></w:r></w:p>
  </w:body>
</w:document>
'''
        path = self._make_docx(xml)
        lines = module.extract_ts_lines(path, mode='auto')
        self.assertEqual(lines, ['00:00:06:28\t00:00:08:11\t大愛真健康'])

    def test_cli_uses_bracket_action_logs(self) -> None:
        xml = '''<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main">
  <w:body>
    <w:p><w:r><w:t>00:00:10:00\t00:00:11:00\t測試</w:t></w:r></w:p>
  </w:body>
</w:document>
'''
        path = self._make_docx(xml)
        env = dict(os.environ)
        env['PYTHONDONTWRITEBYTECODE'] = '1'
        result = subprocess.run(
            [
                'python3',
                str(MODULE_PATH),
                str(path),
                '--mode',
                'all',
                '--out',
                'txt',
                '--force',
            ],
            check=True,
            capture_output=True,
            text=True,
            env=env,
        )
        self.assertIn('[wrote]', result.stdout)


if __name__ == '__main__':
    unittest.main()
