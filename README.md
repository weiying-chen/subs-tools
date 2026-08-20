# subs-tools

Subtitle-related tooling in one place.

## Scripts

- `clean-subs`: clean source markings from DOCX files using the repo venv.
- `rename-subs`: rename generated subtitle DOCX files from `_al_el`, `_al_sy`, or `_al_Shawn` to `_final`.
- `finalize-subs`: clean subtitle DOCX files, export thumbnails, rename to `_final`, then run subtitle analysis once.
- `review-subs`: play a matching video and SRT in Windows MPV with review styling.
- `convert-subs`: convert transcript BODY `.txt` files into `.srt` files.
- `thumbnail_subs.py`: export the DOCX thumbnail image using the English YouTube title.
- `gen_subs.sh`: generate `_al.docx` outputs from `.txt` + source `.docx`.
- `setup_subs.py`: extract subtitle rows, write sectioned `.txt` + raw `.baseline.txt`, and download a linked YouTube video.
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

When a DOCX contains a YouTube or Da Ai video URL, setup copies the resolved URL
with `wl-copy` and downloads the video beside the DOCX with `yt-dlp`, reporting
`[copied]` and `[downloaded]` status lines like `setup-news`.

Finalize generated subtitle DOCX files in current directory and run the subtitle analysis:

```bash
/home/weiying/python/subs-tools/finalize-subs
```

Convert all non-baseline transcript `.txt` files in the current directory to `.srt`:

```bash
/home/weiying/python/subs-tools/convert-subs
```

Review the current directory's matching video and SRT in Windows MPV:

```bash
/home/weiying/python/subs-tools/review-subs
```

When a directory contains one video and multiple SRT files, `review-subs` merges
their existing timeline timestamps into a cached, sorted SRT without changing the
source files. Each source SRT becomes an MPV chapter at its first cue; use
`Ctrl+Left` and `Ctrl+Right` to move between SRT sections.

If multiple candidates exist, pass either the video or SRT explicitly:

```bash
/home/weiying/python/subs-tools/review-subs subtitles.srt
```

Shift every generated subtitle 10 seconds later when the source timecodes are early:

```bash
/home/weiying/python/subs-tools/convert-subs --offset-seconds 10
```

`--offset-seconds` also accepts negative and decimal values. Existing `.srt` files are
overwritten when the command runs.

Export the first referenced DOCX image using the English part of the YouTube title:

```bash
python3 /home/weiying/python/subs-tools/thumbnail_subs.py sample_final.docx
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
