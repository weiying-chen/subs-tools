# subs-tools

Subtitle-related tooling in one place.

## Scripts

- `gen_subs.sh`: generate `_al.docx` outputs from `.txt` + source `.docx`.
- `setup_subs.py`: extract subtitle rows from docx and write sectioned `.txt` + raw `.baseline.txt`.

## Usage

Generate subtitle docx files:

```bash
/home/weiying/python/subs-tools/gen_subs.sh /path/to/target_dir
```

Prepare subtitle files from all docx in current directory (default `--mode auto`):

```bash
python3 /home/weiying/python/subs-tools/setup_subs.py . --force
```

Write only baseline output:

```bash
python3 /home/weiying/python/subs-tools/setup_subs.py . --out baseline --force
```

Extraction mode options:

- `--mode auto` (default): use yellow-highlighted extraction first, then fall back to full-paragraph line parsing if none found.
- `--mode yellow`: only extract from yellow-highlighted runs.
- `--mode all`: extract any full line that matches `start<TAB>end<TAB>text`.
