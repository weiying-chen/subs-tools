import importlib.util
import os
import subprocess
import tempfile
import unittest
import zipfile
from pathlib import Path
import xml.etree.ElementTree as ET


MODULE_PATH = Path('/home/weiying/python/subs-tools/setup_subs.py')
spec = importlib.util.spec_from_file_location('setup_subs', MODULE_PATH)
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

    def test_all_mode_extracts_compact_rows(self) -> None:
        xml = '''<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main">
  <w:body>
    <w:p><w:r><w:t>00:00:10:00</w:t></w:r><w:r><w:t>00:00:11:00</w:t></w:r><w:r><w:t>測試字幕</w:t></w:r></w:p>
  </w:body>
</w:document>
'''
        path = self._make_docx(xml)
        lines = module.extract_ts_lines(path, mode='all')
        self.assertEqual(lines, ['00:00:10:00\t00:00:11:00\t測試字幕'])

    def test_paragraph_text_preserves_word_tab_nodes(self) -> None:
        xml = '''<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main">
  <w:body>
    <w:p>
      <w:r><w:t>00:00:10:00</w:t></w:r>
      <w:r><w:tab/></w:r>
      <w:r><w:t>00:00:11:00</w:t></w:r>
      <w:r><w:tab/></w:r>
      <w:r><w:t>測試字幕</w:t></w:r>
    </w:p>
  </w:body>
</w:document>
'''
        root = ET.fromstring(xml)
        para = root.find('.//w:p', module.NS)
        assert para is not None
        text = module.paragraph_text_with_tabs(para)
        self.assertEqual(text, '00:00:10:00\t00:00:11:00\t測試字幕')

    def test_yellow_mode_extracts_rows_split_across_runs(self) -> None:
        xml = '''<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main">
  <w:body>
    <w:p>
      <w:r><w:rPr><w:highlight w:val="yellow"/></w:rPr><w:t>00:00:10:00</w:t></w:r>
      <w:r><w:rPr><w:highlight w:val="yellow"/></w:rPr><w:tab/></w:r>
      <w:r><w:rPr><w:highlight w:val="yellow"/></w:rPr><w:t>00:00:11:00</w:t></w:r>
      <w:r><w:rPr><w:highlight w:val="yellow"/></w:rPr><w:tab/></w:r>
      <w:r><w:rPr><w:highlight w:val="yellow"/></w:rPr><w:t>測試字幕</w:t></w:r>
    </w:p>
  </w:body>
</w:document>
'''
        path = self._make_docx(xml)
        lines = module.extract_ts_lines(path, mode='yellow')
        self.assertEqual(lines, ['00:00:10:00\t00:00:11:00\t測試字幕'])

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

    def test_render_output_content_formats_non_baseline(self) -> None:
        content = module.render_output_content(
            ['00:00:10:00\t00:00:11:00\t測試字幕'],
            is_baseline=False,
        )
        self.assertTrue(content.startswith('YT_TITLE_SUGGESTED:\nTITLE_SUGGESTED:\n'))
        self.assertIn('\nBODY:\n\n00:00:10:00\t00:00:11:00\t測試字幕\n', content)

    def test_cli_writes_txt_with_sections_and_baseline_raw(self) -> None:
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
        subprocess.run(
            [
                'python3',
                str(MODULE_PATH),
                str(path),
                '--mode',
                'all',
                '--out',
                'both',
                '--force',
            ],
            check=True,
            capture_output=True,
            text=True,
            env=env,
        )
        txt_content = path.with_suffix('.txt').read_text(encoding='utf-8')
        baseline_content = path.with_suffix('.baseline.txt').read_text(encoding='utf-8')
        self.assertIn('BODY:\n\n00:00:10:00\t00:00:11:00\t測試\n', txt_content)
        self.assertTrue(txt_content.startswith('YT_TITLE_SUGGESTED:\n'))
        self.assertEqual(baseline_content, '00:00:10:00\t00:00:11:00\t測試\n')


if __name__ == '__main__':
    unittest.main()
