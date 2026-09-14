# subs-tools

Subtitle-related tooling in one place.

## OCR spacing review

`subocr_spacing.py` builds a local HTML review and an AI-readable `review.json`
from a timed baseline and SubOCR's saved images. Requires Pillow. It suggests
spaces using image gaps; background interference and uncertain glyph alignment
are flagged. Every row remains available for visual review, including rows with
no suggestion. Suggestions are heuristic and must be checked against the images.

```bash
python3 ~/python/subs-tools/subocr_spacing.py build \
  --raw /path/to/block.ocr_raw.jsonl \
  --baseline /path/to/block.baseline.txt \
  --offset 00:07:51 --out /path/to/spacing-review
```

Open `review.html`, adjust suggestions, approve checked rows, and download the
reviewed JSON. An AI can instead inspect the image paths in `review.json`, edit
`suggested`, and set `approved: true` for visually verified rows.

```bash
python3 ~/python/subs-tools/subocr_spacing.py export \
  --review /path/to/reviewed.json \
  --base-corrections /path/to/block.baseline.txt \
  --out /path/to/spacing.corrections.tsv
```

Export rejects approved changes to characters or line structure. The optional
base file preserves existing Chinese corrections; approved spacing takes priority.
Pass the exported TSV to `subocr-to-txt --corrections` on the next generation.
Review generation and export do not edit subtitle files. Preserve a translation
file with work in progress by generating into temporary output paths.

## Scripts

- `clean-subs`: clean source markings from DOCX files using the repo venv.
- `rename-subs`: rename generated subtitle DOCX files from `_al_el`, `_al_sy`, or `_al_Shawn` to `_final`.
- `finalize-subs`: clean subtitle DOCX files, export thumbnails, rename to `_final`, then run subtitle analysis once.
- `review-subs`: play a matching video and SRT in Windows MPV with review styling.
- `ref_subs.py`: build paired pre-edit/post-edit Markdown reference bundles from completed subtitle DOCX files.
- `convert-subs`: convert transcript BODY `.txt` files into `.srt` files.
- `thumbnail_subs.py`: export the DOCX thumbnail image using the English YouTube title.
- `gen_subs.sh`: generate `_al.docx` outputs from `.txt` + source `.docx`.
- `setup_subs.py`: extract subtitle rows, write sectioned `.txt` + raw `.baseline.txt`, and download a linked YouTube video.
- `crop_subs.py`: center-crop images to exact 16:9 in a directory.
- `subocr-to-txt`: convert SubOCR SRT output into `.baseline.txt` and `.txt`,
  applying clean source text and merging identical touching cues after correction.

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

Before discovery, `review-subs` converts each non-baseline TXT file whose matching
SRT file is missing. Existing SRT files are left unchanged.

If multiple candidates exist, pass either the video or SRT explicitly:

```bash
/home/weiying/python/subs-tools/review-subs subtitles.srt
```

Build a subtitle reference bundle from matched `output/*_al.docx` and
`edited/*_final.docx` files:

```bash
python3 /home/weiying/python/subs-tools/ref_subs.py \
  --series 大愛真健康
```

The generator automatically searches batch folders under `~/text/subs`, filters
their matched pairs by the series name, selects the latest six complete folders
(or every available folder when fewer exist), and includes every matched file
within each selected folder. Pass `--latest N` to choose another maximum; the
default is 6, and the filename uses the number actually selected. It normalizes
both DOCX versions back to the standard TXT field
structure. Use `--root` for a different subtitle project,
or `--dry-run`/`--check` to avoid rewriting the reference.

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

Convert SubOCR output into the timed TXT/baseline files:

```bash
/home/weiying/python/subs-tools/subocr-to-txt \
  --srt work/ev31/ocr/block2/ev31_block2_0751-1325.srt \
  --offset 00:07:51 \
  --source "/path/to/source.docx" \
  --start-marker "(2)07:51-13:25" \
  --end-text "帶著孩子們一步一步地去證明他們自己" \
  --taiwan-variants \
  --out-baseline "/path/to/output [2].baseline.txt"
```

After source alignment, correction overrides, and text cleanup, identical
adjacent cues whose timestamps touch are merged into one cue, using the first
start and last end. This removes duplicate rows caused by background text in
OCR. Text must match exactly (including spaces and punctuation); gaps, overlaps,
and intervening different subtitles remain separate. Boundaries with saved
layout lines from `--blank-lines-from` are also retained so notes are not lost.
Both output files use the merged rows, and the command reports the merge count.
Alignment note cue numbers still refer to the original input SRT.

When source alignment finds whole source lines absent from an otherwise matching
OCR cue, conversion stops before writing either output. The error identifies the
source text and any adjacent timing gap (including the clip offset). Check the
saved frames and restore the missing cue in the input SRT before rerunning.
This check catches exact matches after normalization; it does not detect every
OCR omission or infer timing from a gap alone.
The converter also stops if source alignment or a corrections TSV inserts or
deletes even one letter/digit (including Chinese characters), or replaces text
with a different character count. For example, a DOCX-only final `耶` must be
checked against the saved frame before it can enter the output. Equal-length
character corrections, spaces, punctuation, and known OCR noise cleanup remain
allowed. Check flagged changes against the visible subtitle and correct the
source/TSV or restore verified OCR omissions in the input SRT before rerunning.
This is a structural check, not a guarantee that equal-length substitutions
are correct. Both output files remain untouched when the check fails.

Extraction mode options:

- `--mode auto` (default): use yellow-highlighted extraction first, then fall back to full-paragraph line parsing if none found.
- `--mode yellow`: only extract from yellow-highlighted runs.
- `--mode all`: extract any full line that matches `start<TAB>end<TAB>text`.
