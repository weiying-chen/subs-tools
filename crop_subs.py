#!/usr/bin/env python3
import argparse
import shutil
import subprocess
import sys
from pathlib import Path


RATIO_WIDTH = 16
RATIO_HEIGHT = 9
SUPPORTED_SUFFIXES = {'.jpg', '.jpeg', '.png', '.webp', '.tif', '.tiff', '.bmp'}


def missing_magick_message() -> str:
    return (
        '[error] ImageMagick command `magick` was not found in PATH. '
        'Install it and retry, e.g. `sudo apt install -y imagemagick`.'
    )


def compute_center_crop(width: int, height: int) -> tuple[int, int, int, int]:
    if width <= 0 or height <= 0:
        raise ValueError('Image dimensions must be positive integers.')

    scale = min(width // RATIO_WIDTH, height // RATIO_HEIGHT)
    if scale <= 0:
        raise ValueError('Image is too small to crop to 16:9.')

    crop_width = RATIO_WIDTH * scale
    crop_height = RATIO_HEIGHT * scale
    x = (width - crop_width) // 2
    y = (height - crop_height) // 2

    return crop_width, crop_height, x, y


def identify_size(image: Path) -> tuple[int, int]:
    result = subprocess.run(
        ['magick', 'identify', '-format', '%w %h', str(image)],
        check=True,
        capture_output=True,
        text=True,
    )
    width_str, height_str = result.stdout.strip().split()
    return int(width_str), int(height_str)


def crop_image(image: Path, overwrite: bool) -> Path:
    width, height = identify_size(image)
    crop_width, crop_height, x, y = compute_center_crop(width, height)

    if overwrite:
        output_path = image
    else:
        output_path = image.with_name(f'{image.stem}_16x9{image.suffix}')

    subprocess.run(
        [
            'magick',
            str(image),
            '-crop',
            f'{crop_width}x{crop_height}+{x}+{y}',
            '+repage',
            str(output_path),
        ],
        check=True,
    )

    return output_path


def iter_images(directory: Path) -> list[Path]:
    return sorted(
        p for p in directory.iterdir() if p.is_file() and p.suffix.lower() in SUPPORTED_SUFFIXES
    )


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description='Crop images in a directory to exact 16:9 using centered crop.'
    )
    parser.add_argument(
        'directory',
        nargs='?',
        default='.',
        help='Directory to scan (default: current directory).',
    )
    parser.add_argument(
        '--overwrite',
        action='store_true',
        help='Overwrite input files instead of writing *_16x9 outputs.',
    )
    return parser.parse_args()


def main() -> int:
    if shutil.which('magick') is None:
        print(missing_magick_message(), file=sys.stderr)
        return 2

    args = parse_args()
    directory = Path(args.directory).resolve()
    if not directory.is_dir():
        print(f'[error] Not a directory: {directory}', file=sys.stderr)
        return 2

    images = iter_images(directory)
    if not images:
        print(f'[skip] No supported images found in {directory}')
        return 0

    for image in images:
        output = crop_image(image, overwrite=args.overwrite)
        print(f'[wrote] {output}')

    return 0


if __name__ == '__main__':
    raise SystemExit(main())
