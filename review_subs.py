#!/usr/bin/env python3
from __future__ import annotations

import argparse
import hashlib
import platform
import re
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Sequence

import convert_subs


VIDEO_SUFFIXES = {".m4v", ".mkv", ".mov", ".mp4", ".webm"}
TIMESTAMP_RE = re.compile(
    r"^(\d{2}):(\d{2}):(\d{2}),(\d{3})\s+-->\s+"
    r"(\d{2}):(\d{2}):(\d{2}),(\d{3})(.*)$"
)


def media_files(directory: Path) -> tuple[list[Path], list[Path]]:
    videos = sorted(
        path
        for path in directory.iterdir()
        if path.is_file() and path.suffix.lower() in VIDEO_SUFFIXES
    )
    subtitles = sorted(
        path
        for path in directory.iterdir()
        if path.is_file() and path.suffix.lower() == ".srt"
    )
    return videos, subtitles


def prepare_subtitle_files(directory: Path) -> list[Path]:
    generated: list[Path] = []
    sources = sorted(
        path
        for path in directory.iterdir()
        if path.is_file()
        and path.suffix.lower() == ".txt"
        and not path.name.endswith(".baseline.txt")
    )
    for source in sources:
        output = source.with_suffix(".srt")
        if output.is_file():
            continue
        generated.append(convert_subs.convert_txt(source, convert_subs.DEFAULT_FPS))
    return generated


def unique_match(candidates: list[Path], stem: str) -> Path | None:
    matches = [path for path in candidates if path.stem == stem]
    if len(matches) == 1:
        return matches[0]
    return None


def discover_media(
    directory: Path, selected: Path | None = None
) -> tuple[Path, list[Path]]:
    videos, subtitles = media_files(directory)

    if selected is not None:
        selected = selected.expanduser().resolve()
        if not selected.is_file():
            raise ValueError(f"file not found: {selected}")
        if selected.suffix.lower() == ".srt":
            subtitle = selected
            video = unique_match(videos, subtitle.stem)
            if video is None and len(videos) == 1:
                video = videos[0]
            if video is None:
                raise ValueError(f"no unique video matches {subtitle.name}")
            return video, [subtitle]
        if selected.suffix.lower() in VIDEO_SUFFIXES:
            video = selected
            subtitle = unique_match(subtitles, video.stem)
            selected_subtitles = [subtitle] if subtitle is not None else subtitles
            if not selected_subtitles:
                raise ValueError(f"no unique SRT matches {video.name}")
            return video, selected_subtitles
        raise ValueError(f"expected a video or .srt file: {selected}")

    conventional_video = directory / "video.mp4"
    conventional_subtitle = directory / "subtitles.srt"
    if conventional_video.is_file() and conventional_subtitle.is_file():
        return conventional_video, [conventional_subtitle]

    if len(videos) == 1 and subtitles:
        return videos[0], subtitles

    pairs = [
        (video, subtitle)
        for subtitle in subtitles
        for video in videos
        if video.stem == subtitle.stem
    ]
    if len(pairs) == 1:
        video, subtitle = pairs[0]
        return video, [subtitle]
    if len(pairs) > 1:
        raise ValueError("multiple matching video/SRT pairs found; pass one explicitly")
    raise ValueError(
        f"no unique video/SRT pair found ({len(videos)} videos, {len(subtitles)} SRT files)"
    )


def timestamp_milliseconds(match: re.Match[str]) -> int:
    hours, minutes, seconds, milliseconds = (int(value) for value in match.groups()[:4])
    return (((hours * 60) + minutes) * 60 + seconds) * 1000 + milliseconds


def timestamp_end_milliseconds(match: re.Match[str]) -> int:
    hours, minutes, seconds, milliseconds = (int(value) for value in match.groups()[4:8])
    return (((hours * 60) + minutes) * 60 + seconds) * 1000 + milliseconds


def srt_time_bounds(content: str) -> tuple[int, int]:
    matches = [
        match
        for line in content.replace("\r\n", "\n").replace("\r", "\n").splitlines()
        if (match := TIMESTAMP_RE.match(line.strip()))
    ]
    if not matches:
        raise ValueError("SRT contains no timestamp cues")
    return (
        min(timestamp_milliseconds(match) for match in matches),
        max(timestamp_end_milliseconds(match) for match in matches),
    )


def escape_ffmetadata(value: str) -> str:
    return re.sub(r"([\\;#=])", r"\\\1", value).replace("\n", r"\n")


def render_chapters(sources: list[tuple[Path, str]]) -> str:
    chapters = [
        (path, *srt_time_bounds(content))
        for path, content in sources
    ]
    chapters.sort(key=lambda chapter: chapter[1])
    final_end = max(chapter[2] for chapter in chapters)
    lines = [";FFMETADATA1"]
    for index, (path, start_ms, _) in enumerate(chapters):
        end_ms = chapters[index + 1][1] if index + 1 < len(chapters) else final_end
        lines.extend(
            [
                "[CHAPTER]",
                "TIMEBASE=1/1000",
                f"START={start_ms}",
                f"END={max(start_ms + 1, end_ms)}",
                f"title={escape_ffmetadata(path.name)}",
            ]
        )
    return "\n".join(lines) + "\n"


def write_input_config(output: Path) -> None:
    output.write_text(
        "LEFT seek -5 relative+exact\n"
        "RIGHT seek 5 relative+exact\n"
        "Ctrl+LEFT add chapter -1\n"
        "Ctrl+RIGHT add chapter 1\n",
        encoding="utf-8",
    )


def merge_srt_contents(contents: list[str]) -> str:
    cues: list[tuple[int, int, str, list[str]]] = []
    sequence = 0
    for content in contents:
        normalized = content.replace("\r\n", "\n").replace("\r", "\n").strip()
        for block in re.split(r"\n\s*\n", normalized) if normalized else []:
            lines = block.splitlines()
            timestamp_index = 1 if lines and lines[0].strip().isdigit() else 0
            if timestamp_index >= len(lines):
                continue
            timestamp = lines[timestamp_index].strip()
            match = TIMESTAMP_RE.match(timestamp)
            if not match:
                raise ValueError(f"invalid SRT timestamp: {timestamp}")
            text_lines = lines[timestamp_index + 1 :]
            if not text_lines:
                continue
            cues.append(
                (timestamp_milliseconds(match), sequence, timestamp, text_lines)
            )
            sequence += 1

    cues.sort(key=lambda cue: (cue[0], cue[1]))
    blocks = [
        "\n".join([str(index), timestamp, *text_lines])
        for index, (_, _, timestamp, text_lines) in enumerate(cues, start=1)
    ]
    return "\n\n".join(blocks) + ("\n" if blocks else "")


def combined_subtitle_path(directory: Path, cache_root: Path) -> Path:
    key = hashlib.sha256(str(directory.resolve()).encode("utf-8")).hexdigest()[:16]
    return cache_root / key / "combined.srt"


def prepare_subtitle(subtitles: list[Path], directory: Path) -> Path:
    if len(subtitles) == 1:
        return subtitles[0]
    output = combined_subtitle_path(
        directory,
        Path.home() / ".cache" / "review-subs",
    )
    output.parent.mkdir(parents=True, exist_ok=True)
    content = merge_srt_contents(
        [path.read_text(encoding="utf-8-sig") for path in subtitles]
    )
    output.write_text(content, encoding="utf-8")
    return output


def prepare_player_files(
    subtitles: list[Path], directory: Path
) -> tuple[Path, Path, Path]:
    subtitle = prepare_subtitle(subtitles, directory)
    cache_directory = combined_subtitle_path(
        directory,
        Path.home() / ".cache" / "review-subs",
    ).parent
    cache_directory.mkdir(parents=True, exist_ok=True)
    sources = [
        (path, path.read_text(encoding="utf-8-sig"))
        for path in subtitles
    ]
    chapters = cache_directory / "chapters.ffmetadata"
    chapters.write_text(render_chapters(sources), encoding="utf-8")
    input_config = cache_directory / "input.conf"
    write_input_config(input_config)
    return subtitle, chapters, input_config


def build_mpv_command(
    *,
    mpv: str,
    video: Path | str,
    subtitle: Path | str,
    chapters: Path | str,
    input_config: Path | str,
) -> list[str]:
    return [
        mpv,
        f"--sub-file={subtitle}",
        f"--chapters-file={chapters}",
        f"--input-conf={input_config}",
        "--sub-font-size=48",
        "--sub-border-style=background-box",
        "--sub-back-color=#C0000000",
        "--autofit=1280x720",
        "--geometry=50%:50%",
        "--focus-on=all",
        "--keep-open=yes",
        str(video),
    ]


def running_in_wsl() -> bool:
    return "microsoft" in platform.release().lower()


def find_windows_mpv() -> str:
    executable = shutil.which("mpv.exe")
    if executable:
        return executable
    installed = Path("/mnt/c/Program Files/MPV Player/mpv.exe")
    if installed.is_file():
        return str(installed)
    raise RuntimeError(
        "Windows mpv not found; install it with: "
        "winget.exe install --id shinchiro.mpv --exact"
    )


def to_windows_path(path: Path) -> str:
    result = subprocess.run(
        ["wslpath", "-w", str(path)],
        check=True,
        capture_output=True,
        text=True,
    )
    return result.stdout.strip()


def play_video(
    video: Path, subtitle: Path, chapters: Path, input_config: Path
) -> None:
    if running_in_wsl():
        mpv = find_windows_mpv()
        rendered_video: Path | str = to_windows_path(video)
        rendered_subtitle: Path | str = to_windows_path(subtitle)
        rendered_chapters: Path | str = to_windows_path(chapters)
        rendered_input_config: Path | str = to_windows_path(input_config)
    else:
        mpv = shutil.which("mpv") or ""
        if not mpv:
            raise RuntimeError("required program not found in PATH: mpv")
        rendered_video = video
        rendered_subtitle = subtitle
        rendered_chapters = chapters
        rendered_input_config = input_config
    subprocess.run(
        build_mpv_command(
            mpv=mpv,
            video=rendered_video,
            subtitle=rendered_subtitle,
            chapters=rendered_chapters,
            input_config=rendered_input_config,
        ),
        check=True,
    )


def create_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Play a matching video and SRT from the current directory."
    )
    parser.add_argument(
        "media",
        nargs="?",
        type=Path,
        help="Video or SRT to review (default: discover a unique pair in cwd).",
    )
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = create_parser().parse_args(argv)
    try:
        directory = Path.cwd()
        generated_subtitles = prepare_subtitle_files(directory)
        for path in generated_subtitles:
            print(f"[converted] {path.name}")
        video, subtitles = discover_media(directory, args.media)
        subtitle, chapters, input_config = prepare_player_files(subtitles, directory)
        print(f"[video] {video.name}")
        if len(subtitles) == 1:
            print(f"[subtitles] {subtitle.name}")
        else:
            print(f"[subtitles] merged {len(subtitles)} files: {subtitle}")
        print(f"[chapters] {len(subtitles)} SRT boundaries")
        play_video(video, subtitle, chapters, input_config)
    except (OSError, RuntimeError, ValueError, subprocess.CalledProcessError) as error:
        print(f"[error] {error}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
