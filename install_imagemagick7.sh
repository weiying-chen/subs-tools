#!/usr/bin/env bash
set -euo pipefail

echo "[1/6] Installing build dependencies"
sudo apt update
sudo apt install -y \
  build-essential pkg-config git \
  libjpeg-dev libpng-dev libtiff-dev libwebp-dev libheif-dev \
  libxml2-dev libfreetype6-dev liblcms2-dev libltdl-dev zlib1g-dev

echo "[2/6] Fetching ImageMagick source"
cd /tmp
rm -rf ImageMagick
git clone --depth 1 https://github.com/ImageMagick/ImageMagick.git
cd ImageMagick

echo "[3/6] Configuring build"
./configure --with-modules

echo "[4/6] Building"
make -j"$(nproc)"

echo "[5/6] Installing"
sudo make install
sudo ldconfig

echo "[6/6] Verifying"
/usr/local/bin/magick -version || true

if command -v magick >/dev/null 2>&1; then
  echo "[ok] magick found on PATH"
  magick -version
else
  echo "[warn] /usr/local/bin/magick installed but not on PATH"
  echo "       Run: echo 'export PATH=/usr/local/bin:\$PATH' >> ~/.bashrc && source ~/.bashrc"
fi
