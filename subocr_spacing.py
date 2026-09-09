#!/usr/bin/env python3
"""Build image-backed subtitle spacing reviews and export approved corrections."""
from __future__ import annotations

import argparse
import base64
import html
import io
import json
import re
import statistics
from pathlib import Path

from PIL import Image


TIME = re.compile(r'^\d{2}:\d{2}:\d{2}:\d{2}$')


def seconds(value: str) -> float:
    parts = value.split(':')
    if len(parts) not in (3, 4):
        raise ValueError('Expected HH:MM:SS or HH:MM:SS:FF (30 fps)')
    return int(parts[0])*3600 + int(parts[1])*60 + float(parts[2]) + (int(parts[3])/30 if len(parts) == 4 else 0)


def suggest_spacing(image: Image.Image, text: str) -> dict:
    """Conservative column projection; ambiguous glyph correspondence is withheld."""
    gray = image.convert('L')
    width, height = gray.size
    pixels = gray.load()
    active = [sum(pixels[x, y] >= 210 for y in range(height)) >= 1 for x in range(width)]
    # Close tiny gaps inside glyphs, but preserve likely inter-character gaps.
    for x in range(1, width-2):
        if active[x-1] and not active[x]:
            for distance in (1, 2):
                if x+distance < width and active[x+distance]:
                    active[x:x+distance] = [True]*distance
                    break
    runs = []
    start = None
    for x, enabled in enumerate(active + [False]):
        if enabled and start is None:
            start = x
        elif not enabled and start is not None:
            if x-start >= 4:
                runs.append((start, x))
            start = None
    compact = text.replace(' ', '')
    result = dict(suggested=None, status='needs-review', gaps=[], reason='Glyph count or background is ambiguous')
    if len(runs) != len(compact) or len(runs) < 3 or any(ord(c) < 0x3000 for c in compact):
        return result
    widths = [b-a for a,b in runs]
    typical = statistics.median(widths)
    if min(widths) < typical*.45 or max(widths) > typical*1.65:
        return result
    gaps = [runs[i+1][0]-runs[i][1] for i in range(len(runs)-1)]
    normal = statistics.median(gaps)
    proposed = {i+1 for i, gap in enumerate(gaps) if gap > max(normal*1.8, normal+typical*.25)}
    existing = set()
    count = 0
    for char in text:
        if char == ' ':
            existing.add(count)
        else:
            count += 1
    positions = proposed | existing
    suggested = ''.join((' ' if i in positions else '') + char for i,char in enumerate(compact))
    result.update(suggested=suggested, status='candidate' if suggested != text else 'no-new-gap',
                  reason='Image gaps mapped to glyphs; visual confirmation required',
                  gaps=[dict(after=i, x=(runs[i-1][1]+runs[i][0])/2) for i in sorted(proposed)])
    return result


def export_corrections(rows: list[dict]) -> str:
    lines = []
    seen = set()
    for row in rows:
        if not row.get('approved'):
            continue
        start, current, suggested = row['start'], row['current'], row.get('suggested')
        if not TIME.fullmatch(start) or start in seen:
            raise ValueError('Invalid or duplicate approved timestamp')
        if not isinstance(suggested, str) or any(c in suggested for c in '\r\n\t'):
            raise ValueError('Approved text must be a single line')
        if current.replace(' ', '') != suggested.replace(' ', ''):
            raise ValueError('Spacing review may change spaces only: ' + start)
        seen.add(start)
        lines.append(start+'\t'+suggested)
    return '\n'.join(lines) + ('\n' if lines else '')


def build(args):
    root = args.raw.parent.resolve()
    records = [json.loads(line) for line in args.raw.read_text(encoding='utf-8').splitlines() if line.strip()]
    offset = seconds(args.offset)
    rows = []
    for line in args.baseline.read_text(encoding='utf-8-sig').splitlines():
        fields = line.split('\t', 2)
        if len(fields) != 3 or not TIME.fullmatch(fields[0]):
            continue
        start, end, current = fields
        lo, hi = seconds(start)-offset, seconds(end)-offset
        matches = [r for r in records if lo-.001 <= r['timestamp'] < hi]
        row = dict(start=start, end=end, current=current, approved=False, images=[])
        if not matches:
            row.update(suggested=None, status='needs-review', reason='No OCR frame inside this cue', gaps=[])
        else:
            # Include early and later frames so transitions remain inspectable.
            chosen = [matches[0]]
            if matches[-1]['frame_path'] != matches[0]['frame_path']:
                chosen.append(matches[-1])
            analyses = []
            for record in chosen:
                path = (root / record['frame_path']).resolve()
                if not path.is_relative_to(root):
                    raise ValueError('Frame path escapes OCR directory')
                with Image.open(path) as image:
                    analyses.append(suggest_spacing(image, current))
                    data = io.BytesIO()
                    image.save(data, format='PNG')
                    row['images'].append(dict(path=str(path), timestamp=record['timestamp'],
                                              data=base64.b64encode(data.getvalue()).decode()))
            candidates = [a for a in analyses if a['status'] == 'candidate']
            row.update(candidates[0] if candidates else analyses[0])
            if len({a['suggested'] for a in analyses}) > 1:
                row['status'] = 'needs-review'
                row['reason'] = 'Frames disagree; check the proposed spacing visually'
        rows.append(row)
    args.out.mkdir(parents=True, exist_ok=True)
    review = dict(version=1, baseline=str(args.baseline.resolve()), rows=rows)
    cards = []
    for i, row in enumerate(rows):
        imgs = ''.join('<img src="data:image/png;base64,'+im['data']+'">' for im in row['images'])
        cards.append(f'<article><h2>{i+1}. {row["start"]} &ndash; {row["end"]}</h2>'
                     f'<p>{html.escape(row["status"])}: {html.escape(row["reason"])}</p>{imgs}'
                     f'<p>Current: <span>{html.escape(row["current"])}</span></p>'
                     f'<label>Suggested: <input data-index="{i}" value="{html.escape(row["suggested"] or row["current"], quote=True)}"></label>'
                     f'<label><input type="checkbox" data-approve="{i}"> Approve</label></article>')
    payload = json.dumps(review, ensure_ascii=True).replace('<', '\\u003c')
    page = '''<!doctype html><meta charset="utf-8"><title>Subtitle spacing review</title>
<style>body{font:16px sans-serif;margin:24px;color:#222;background:#fff}article{border-bottom:1px solid #bbb;padding:12px 0}h2{font-size:18px}img{display:block;max-width:100%;height:auto;margin:8px 0}span,input{white-space:pre-wrap}input[data-index]{display:block;width:95%;font-size:20px;padding:6px}label{display:block;margin:8px 0}button{position:sticky;top:8px;padding:10px;background:#fff;border:1px solid #555}</style>
<button id="download">Download reviewed JSON</button>'''+''.join(cards)+'''
<script>const review='''+payload+''';
document.querySelector('#download').onclick=()=>{
 document.querySelectorAll('[data-index]').forEach(e=>review.rows[+e.dataset.index].suggested=e.value);
 document.querySelectorAll('[data-approve]').forEach(e=>review.rows[+e.dataset.approve].approved=e.checked);
 const url=URL.createObjectURL(new Blob([JSON.stringify(review,null,2)],{type:'application/json'}));
 const a=document.createElement('a');a.href=url;a.download='reviewed.json';a.click();setTimeout(()=>URL.revokeObjectURL(url),1000);
};</script>'''
    (args.out/'review.html').write_text(page, encoding='utf-8')
    for row in rows:
        for im in row['images']:
            del im['data']
    (args.out/'review.json').write_text(json.dumps(review, ensure_ascii=False, indent=2)+'\n', encoding='utf-8')
    print(f'{len(rows)} rows; {sum(r["status"] == "candidate" for r in rows)} candidates; '
          f'{sum(r["status"] == "needs-review" for r in rows)} uncertain')
    print(args.out/'review.html')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest='command', required=True)
    review = commands.add_parser('build')
    review.add_argument('--raw', type=Path, required=True, help='SubOCR ocr_raw.jsonl with saved frames')
    review.add_argument('--baseline', type=Path, required=True)
    review.add_argument('--offset', required=True, help='Absolute clip start HH:MM:SS')
    review.add_argument('--out', type=Path, required=True, help='Review output directory')
    export = commands.add_parser('export')
    export.add_argument('--review', type=Path, required=True)
    export.add_argument('--out', type=Path, required=True, help='Approved corrections TSV')
    export.add_argument('--base-corrections', type=Path, help='Existing corrections or baseline TSV to preserve')
    args = parser.parse_args()
    try:
        if args.command == 'build':
            build(args)
        else:
            content = export_corrections(json.loads(args.review.read_text(encoding='utf-8'))['rows'])
            if args.base_corrections:
                merged = {}
                for line in args.base_corrections.read_text(encoding='utf-8-sig').splitlines():
                    fields = line.split('\t')
                    if len(fields) >= 2 and TIME.fullmatch(fields[0]):
                        merged[fields[0]] = fields[-1]
                for line in content.splitlines():
                    start, text = line.split('\t', 1)
                    merged[start] = text
                content = ''.join(start+'\t'+merged[start]+'\n' for start in sorted(merged))
            args.out.write_text(content, encoding='utf-8')
            print(args.out)
    except (ValueError, OSError, KeyError) as error:
        parser.exit(1, f'error: {error}\n')


if __name__ == '__main__':
    main()
