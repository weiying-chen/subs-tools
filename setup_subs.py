#!/usr/bin/env python3
from __future__ import annotations

import argparse
import re
import shutil
import subprocess
import sys
import urllib.error
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
import zipfile
from pathlib import Path

W_NS = "http://schemas.openxmlformats.org/wordprocessingml/2006/main"
NS = {"w": W_NS}
R_NS = "http://schemas.openxmlformats.org/package/2006/relationships"
R_NS_MAP = {"r": R_NS}

# In current files, yellow-highlighted runs often store: <start><end><zh_text>
HIGHLIGHTED_LINE_RE = re.compile(
    r"^(\d{2}:\d{2}:\d{2}:\d{2})(\d{2}:\d{2}:\d{2}:\d{2})(.+)$"
)
# Some files keep subtitle rows as full lines in paragraph text.
PARAGRAPH_TAB_LINE_RE = re.compile(
    r"^(\d{2}:\d{2}:\d{2}:\d{2})\t+(\d{2}:\d{2}:\d{2}:\d{2})\t+(.+)$"
)
PARAGRAPH_COMPACT_LINE_RE = re.compile(
    r"^(\d{2}:\d{2}:\d{2}:\d{2})(\d{2}:\d{2}:\d{2}:\d{2})(.+)$"
)
HAS_CHINESE_RE = re.compile(r"[\u4e00-\u9fff]")
URL_RE = re.compile(r"https?://[^\s<>()\"']+")
YOUTUBE_ID_RE = re.compile(
    r'\\"?YTID\\"?\s*:\s*\\"?([A-Za-z0-9_-]{11})\\"?'
)
NEWS_ID_RE = re.compile(r'\\"?NewsID\\"?\s*:\s*(\d+)')
NEWS_JSON_RE = re.compile(r"var\s+newsJson\s*=\s*'([^\r\n]*)")


def load_docx_root(docx_path: Path) -> ET.Element:
    with zipfile.ZipFile(docx_path) as zf:
        xml = zf.read("word/document.xml")
    return ET.fromstring(xml)


def find_first_url_in_root(root: ET.Element) -> str:
    for para in root.findall(".//w:p", NS):
        text = "".join(node.text or "" for node in para.findall(".//w:t", NS))
        match = URL_RE.search(text)
        if match:
            return match.group(0).rstrip(".,;:!?)）]}")
    return ""


def extract_docx_hyperlink_urls(docx_path: Path) -> list[str]:
    with zipfile.ZipFile(docx_path) as zf:
        try:
            rels_xml = zf.read("word/_rels/document.xml.rels")
        except KeyError:
            return []

    root = ET.fromstring(rels_xml)
    urls: list[str] = []
    for rel in root.findall(".//r:Relationship", R_NS_MAP):
        target = (rel.get("Target") or "").strip()
        target_mode = (rel.get("TargetMode") or "").strip()
        if target_mode.lower() == "external" and target.lower().startswith(
            ("http://", "https://")
        ):
            urls.append(target)
    return urls


def find_first_docx_url(docx_path: Path) -> str:
    first_url = find_first_url_in_root(load_docx_root(docx_path))
    if first_url:
        return first_url
    hyperlink_urls = extract_docx_hyperlink_urls(docx_path)
    return hyperlink_urls[0] if hyperlink_urls else ""


def copy_to_clipboard(text: str, copy_cmd: str = "wl-copy") -> bool:
    try:
        subprocess.run([copy_cmd], input=(text + "\n").encode("utf-8"), check=True)
        return True
    except (FileNotFoundError, subprocess.CalledProcessError):
        return False


def extract_youtube_url_from_daai_html(
    html_text: str, news_id: str | None = None
) -> str:
    candidates = NEWS_JSON_RE.findall(html_text) or [html_text]
    for candidate in candidates:
        if news_id:
            id_match = NEWS_ID_RE.search(candidate)
            if not id_match or id_match.group(1) != news_id:
                continue
        youtube_match = YOUTUBE_ID_RE.search(candidate)
        if youtube_match:
            return f"https://www.youtube.com/watch?v={youtube_match.group(1)}"
    return ""


def resolve_youtube_url(source_url: str, timeout: float = 30.0) -> str:
    hostname = (urllib.parse.urlparse(source_url).hostname or "").lower()
    if hostname == "youtu.be" or hostname == "youtube.com" or hostname.endswith(
        ".youtube.com"
    ):
        return source_url
    if hostname == "tcmaster.daai.tv":
        return source_url
    if hostname != "daai.tv" and not hostname.endswith(".daai.tv"):
        return ""

    request = urllib.request.Request(source_url, headers={"User-Agent": "Mozilla/5.0"})
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            html_text = response.read().decode("utf-8", errors="replace")
    except (OSError, urllib.error.URLError) as error:
        raise RuntimeError(f"failed to load Da Ai page: {error}") from error

    path_parts = urllib.parse.urlparse(source_url).path.rstrip("/").split("/")
    news_id = path_parts[-1] if path_parts[-1].isdigit() else None
    youtube_url = extract_youtube_url_from_daai_html(html_text, news_id=news_id)
    if not youtube_url:
        raise RuntimeError("Da Ai page does not contain a YouTube video ID")
    return youtube_url


def build_youtube_download_command(youtube_url: str, workspace: Path) -> list[str]:
    return [
        "yt-dlp",
        "--no-playlist",
        "--paths",
        str(workspace),
        youtube_url,
    ]


def download_youtube_video(youtube_url: str, workspace: Path) -> None:
    if not shutil.which("yt-dlp"):
        raise RuntimeError("required program not found in PATH: yt-dlp")
    subprocess.run(build_youtube_download_command(youtube_url, workspace), check=True)


def paragraph_text_with_tabs(para: ET.Element) -> str:
    parts: list[str] = []
    for node in para.iter():
        if node.tag == f"{{{W_NS}}}tab":
            parts.append("\t")
        elif node.tag == f"{{{W_NS}}}t":
            parts.append(node.text or "")
    return "".join(parts).strip()


def run_is_yellow(run: ET.Element) -> bool:
    hl = run.find("./w:rPr/w:highlight", NS)
    return hl is not None and hl.attrib.get(f"{{{W_NS}}}val") == "yellow"


def yellow_paragraph_text_with_tabs(para: ET.Element) -> str:
    parts: list[str] = []
    for run in para.findall(".//w:r", NS):
        if not run_is_yellow(run):
            continue
        for node in run.iter():
            if node.tag == f"{{{W_NS}}}tab":
                parts.append("\t")
            elif node.tag == f"{{{W_NS}}}t":
                parts.append(node.text or "")
    return "".join(parts).strip()


def normalize_compact_text(text: str) -> str:
    # Normalize BOM/zero-width/no-break characters frequently found in Word runs.
    return (
        text.replace("\ufeff", "")
        .replace("\u200b", "")
        .replace("\u00a0", " ")
        .replace(" ", "")
    )


def extract_ts_lines_from_yellow(root: ET.Element) -> list[str]:
    out: list[str] = []

    for para in root.findall(".//w:p", NS):
        text = yellow_paragraph_text_with_tabs(para)
        if not text:
            continue

        parsed = parse_paragraph_row(text)
        if parsed is None:
            continue

        start, end, zh = parsed
        if not HAS_CHINESE_RE.search(zh):
            continue

        out.append(f"{start}\t{end}\t{zh}")

    return out


def parse_paragraph_row(text: str) -> tuple[str, str, str] | None:
    tab_match = PARAGRAPH_TAB_LINE_RE.match(text)
    if tab_match:
        return tab_match.group(1), tab_match.group(2), tab_match.group(3)

    # Fallback for compact rows where docx text is concatenated without tabs.
    normalized = normalize_compact_text(text)
    compact_match = PARAGRAPH_COMPACT_LINE_RE.match(normalized)
    if compact_match:
        return compact_match.group(1), compact_match.group(2), compact_match.group(3)

    return None


def extract_ts_lines_from_paragraphs_with_any_yellow(root: ET.Element) -> list[str]:
    out: list[str] = []

    for para in root.findall(".//w:p", NS):
        has_yellow = any(run_is_yellow(run) for run in para.findall('.//w:r', NS))
        if not has_yellow:
            continue

        text = paragraph_text_with_tabs(para)
        if not text:
            continue

        parsed = parse_paragraph_row(text)
        if parsed is None:
            continue

        start, end, zh = parsed
        if not HAS_CHINESE_RE.search(zh):
            continue

        out.append(f"{start}\t{end}\t{zh}")

    return out


def extract_ts_lines_from_all_paragraphs(root: ET.Element) -> list[str]:
    out: list[str] = []

    for para in root.findall(".//w:p", NS):
        text = paragraph_text_with_tabs(para)
        if not text:
            continue

        parsed = parse_paragraph_row(text)
        if parsed is None:
            continue

        start, end, zh = parsed
        if not HAS_CHINESE_RE.search(zh):
            continue

        out.append(f"{start}\t{end}\t{zh}")

    return out


def extract_ts_lines(docx_path: Path, mode: str = "auto") -> list[str]:
    root = load_docx_root(docx_path)

    if mode == "yellow":
        return extract_ts_lines_from_yellow(root)

    if mode == "all":
        return extract_ts_lines_from_all_paragraphs(root)

    # auto: prefer yellow-highlighted extraction, and keep rows from
    # paragraphs that contain yellow runs (for partial-highlight rows).
    yellow_lines = extract_ts_lines_from_yellow(root)
    if not yellow_lines:
        return extract_ts_lines_from_all_paragraphs(root)

    para_yellow_lines = extract_ts_lines_from_paragraphs_with_any_yellow(root)
    merged: list[str] = []
    seen: set[str] = set()
    for line in para_yellow_lines + yellow_lines:
        if line in seen:
            continue
        seen.add(line)
        merged.append(line)
    return merged


def render_output_content(lines: list[str], *, is_baseline: bool) -> str:
    if is_baseline:
        return "\n".join(lines) + ("\n" if lines else "")

    sections = [
        "YT_TITLE_SUGGESTED:",
        "",
        "TITLE_SUGGESTED:",
        "",
        "INTRO:",
        "",
        "THUMBNAIL:",
        "",
        "BODY:",
    ]
    body = "\n".join(lines)
    content = "\n".join(sections)
    if body:
        content = f"{content}\n\n{body}"
    return content + "\n"


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(
        description=(
            "Extract timestamp rows from docx files. "
            "Default mode prefers yellow-highlighted runs and falls back to all paragraphs."
        )
    )
    p.add_argument(
        "paths",
        nargs="*",
        type=Path,
        help="Docx file(s) or directory(ies). Defaults to current directory.",
    )
    p.add_argument(
        "--force",
        action="store_true",
        help="Overwrite existing outputs.",
    )
    p.add_argument(
        "--out",
        choices=["both", "txt", "baseline"],
        default="both",
        help="Which output files to write.",
    )
    p.add_argument(
        "--mode",
        choices=["auto", "yellow", "all"],
        default="auto",
        help="Extraction mode: auto (yellow then fallback), yellow, or all paragraphs.",
    )
    return p.parse_args()


def gather_docx_paths(paths: list[Path]) -> list[Path]:
    if not paths:
        paths = [Path.cwd()]

    out: list[Path] = []
    for p in paths:
        if p.is_dir():
            out.extend(
                sorted(
                    docx_path
                    for docx_path in p.glob("*.docx")
                    if not docx_path.name.startswith("~$")
                )
            )
        elif p.is_file() and p.suffix.lower() == ".docx":
            if p.name.startswith("~$"):
                continue
            out.append(p)

    # de-dup while preserving order
    seen: set[Path] = set()
    uniq: list[Path] = []
    for p in out:
        rp = p.resolve()
        if rp not in seen:
            seen.add(rp)
            uniq.append(p)
    return uniq


def main() -> int:
    args = parse_args()
    docx_paths = gather_docx_paths(args.paths)
    if not docx_paths:
        print("[error] no .docx files found")
        return 2

    handled_video_urls: set[str] = set()
    for docx_path in docx_paths:
        try:
            lines = extract_ts_lines(docx_path, mode=args.mode)
            first_url = find_first_docx_url(docx_path)
        except (zipfile.BadZipFile, KeyError, ET.ParseError) as exc:
            print(f"[skip] invalid docx: {docx_path} ({exc})")
            continue

        out_paths: list[Path] = []
        if args.out in ("both", "txt"):
            out_paths.append(docx_path.with_suffix(".txt"))
        if args.out in ("both", "baseline"):
            out_paths.append(docx_path.with_suffix(".baseline.txt"))

        for out_path in out_paths:
            if out_path.exists() and not args.force:
                print(f"[skip] exists: {out_path}")
                continue
            content = render_output_content(
                lines, is_baseline=out_path.name.endswith(".baseline.txt")
            )
            out_path.write_text(content, encoding="utf-8")
            print(f"[wrote] {out_path} ({len(lines)} lines)")

        if first_url:
            try:
                youtube_url = resolve_youtube_url(first_url)
            except RuntimeError as error:
                print(f"[error] {error}", file=sys.stderr)
                return 1

            clipboard_url = youtube_url or first_url
            if clipboard_url in handled_video_urls:
                print(f"[skip] video URL already handled: {clipboard_url}")
                continue
            handled_video_urls.add(clipboard_url)

            if copy_to_clipboard(clipboard_url):
                print(f"[copied] {clipboard_url}")
            else:
                print(
                    "[warn] URL found but failed to copy with wl-copy",
                    file=sys.stderr,
                )

            if youtube_url:
                try:
                    download_youtube_video(youtube_url, docx_path.parent)
                except (RuntimeError, subprocess.CalledProcessError) as error:
                    print(f"[error] video download failed: {error}", file=sys.stderr)
                    return 1
                print(f"[downloaded] {youtube_url}")
            else:
                print(f"[warn] no YouTube link found: {first_url}", file=sys.stderr)

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
