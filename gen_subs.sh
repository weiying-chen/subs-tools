#!/usr/bin/env bash
set -euo pipefail

usage() {
  cat <<'EOF'
Usage:
  gen_subs.sh [target_dir]

For each *.txt in target_dir (excluding *.baseline.txt):
  - source docx: <same-basename>.docx
  - output docx: output/<same-basename>_al.docx

Environment overrides:
  GENERATE_SUBS_SCRIPT   default: $HOME/python/word/generate_subs.py
  GENERATE_SUBS_PYTHON   default: $HOME/python/word/.venv/bin/python
  GENERATE_SUBS_TEMPLATE default: $HOME/python/word/templates/subs_template.docx
EOF
}

if [[ "${1:-}" == "-h" || "${1:-}" == "--help" ]]; then
  usage
  exit 0
fi

TARGET_DIR="${1:-.}"
SCRIPT_PATH="${GENERATE_SUBS_SCRIPT:-$HOME/python/word/generate_subs.py}"
PYTHON_BIN="${GENERATE_SUBS_PYTHON:-$HOME/python/word/.venv/bin/python}"
TEMPLATE_PATH="${GENERATE_SUBS_TEMPLATE:-$HOME/python/word/templates/subs_template.docx}"
OUTPUT_DIR="${TARGET_DIR%/}/output"

if [[ ! -d "$TARGET_DIR" ]]; then
  echo "[error] target directory not found: $TARGET_DIR" >&2
  exit 1
fi

if [[ ! -f "$SCRIPT_PATH" ]]; then
  echo "[error] generate_subs script not found: $SCRIPT_PATH" >&2
  exit 1
fi

if [[ ! -x "$PYTHON_BIN" ]]; then
  echo "[error] python binary not executable: $PYTHON_BIN" >&2
  exit 1
fi

if [[ ! -f "$TEMPLATE_PATH" ]]; then
  echo "[error] template not found: $TEMPLATE_PATH" >&2
  exit 1
fi

mkdir -p "$OUTPUT_DIR"

shopt -s nullglob
mapfile -t txt_files < <(
  find "$TARGET_DIR" -maxdepth 1 -type f -name '*.txt' ! -name '*.baseline.txt' | sort
)

if [[ ${#txt_files[@]} -eq 0 ]]; then
  echo "[skip] no .txt files found in: $TARGET_DIR"
  exit 0
fi

processed=0
skipped=0

for txt in "${txt_files[@]}"; do
  txt_name="$(basename "$txt")"
  base_name="${txt_name%.txt}"
  src="${TARGET_DIR%/}/${base_name}.docx"
  out="${OUTPUT_DIR}/${base_name}.docx"

  if [[ ! -f "$src" ]]; then
    echo "[skip] missing source docx: $txt_name" >&2
    ((skipped+=1))
    continue
  fi

  "$PYTHON_BIN" "$SCRIPT_PATH" \
    --template "$TEMPLATE_PATH" \
    --source-docx "$src" \
    --input "$txt" \
    --output "$out"

  generated_path="${out%.docx}_al.docx"
  echo "[created] $(basename "$generated_path")"
  ((processed+=1))
 done

copied_png=0
for png in "$TARGET_DIR"/*.png; do
  dest_png="${OUTPUT_DIR}/$(basename "$png")"
  cp -f -- "$png" "$dest_png"
  echo "[copied] $(basename "$png")"
  ((copied_png+=1))
 done

echo "[summary] generated=$processed copied_png=$copied_png skipped=$skipped"
