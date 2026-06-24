# subs-tools

Subtitle-related tooling in one place.

## Scripts

- `clean-subs`: clean source markings from DOCX files using the repo venv.
- `rename-subs`: rename generated subtitle DOCX files from `_al` or `_al_el` to `_final`.
- `finalize-subs`: run subtitle cleanup first, then rename the cleaned DOCX to `_final`.
- `convert-subs`: convert transcript BODY `.txt` files into `.srt` files.
- `gen_subs.sh`: generate `_al.docx` outputs from `.txt` + source `.docx`, then crop images in the same directory to 16:9.
- `setup_subs.py`: extract subtitle rows from docx and write sectioned `.txt` + raw `.baseline.txt`.
- `crop_subs.py`: center-crop images to exact 16:9 in a directory.

## Usage

Generate subtitle docx files:

```bash
/home/weiying/python/subs-tools/gen_subs.sh /path/to/target_dir
```

Prepare subtitle files from all docx in current directory (default `--mode auto`):

```bash
python3 /home/weiying/python/subs-tools/setup_subs.py . --force
```

Finalize generated subtitle DOCX files in current directory:

```bash
/home/weiying/python/subs-tools/finalize-subs
```

Convert all non-baseline transcript `.txt` files in the current directory to `.srt`:

```bash
/home/weiying/python/subs-tools/convert-subs
```

Rename generated subtitle DOCX files without cleaning:

```bash
/home/weiying/python/subs-tools/rename-subs
```

Write only baseline output:

```bash
python3 /home/weiying/python/subs-tools/setup_subs.py . --out baseline --force
```

Crop images in current directory to exact 16:9 (writes `*_16x9` files):

```bash
python3 /home/weiying/python/subs-tools/crop_subs.py .
```

Crop and overwrite originals:

```bash
python3 /home/weiying/python/subs-tools/crop_subs.py . --overwrite
```

Extraction mode options:

- `--mode auto` (default): use yellow-highlighted extraction first, then fall back to full-paragraph line parsing if none found.
- `--mode yellow`: only extract from yellow-highlighted runs.
- `--mode all`: extract any full line that matches `start<TAB>end<TAB>text`.
