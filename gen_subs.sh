#!/usr/bin/env bash
set -uo pipefail

usage() {
  cat <<'EOF2'
Usage:
  gen-subs [target_dir]

For each *.txt in target_dir (excluding *.baseline.txt):
  - source docx: <same-basename>.docx
  - output docx: output/<same-basename>_al.docx

Environment overrides:
  GENERATE_SUBS_SCRIPT   default: $HOME/python/word/generate_subs.py
  GENERATE_SUBS_PYTHON   default: $HOME/python/word/.venv/bin/python
  GENERATE_SUBS_TEMPLATE default: $HOME/python/word/templates/subs_template.docx
  GENERATE_SUBS_CROP_SCRIPT default: $HOME/python/subs-tools/crop_subs.py
EOF2
}

if [[ "${1:-}" == "-h" || "${1:-}" == "--help" ]]; then
  usage
  exit 0
fi

TARGET_DIR="${1:-.}"
SCRIPT_PATH="${GENERATE_SUBS_SCRIPT:-$HOME/python/word/generate_subs.py}"
PYTHON_BIN="${GENERATE_SUBS_PYTHON:-$HOME/python/word/.venv/bin/python}"
TEMPLATE_PATH="${GENERATE_SUBS_TEMPLATE:-$HOME/python/word/templates/subs_template.docx}"
CROP_SCRIPT_PATH="${GENERATE_SUBS_CROP_SCRIPT:-$HOME/python/subs-tools/crop_subs.py}"
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

if [[ ! -f "$CROP_SCRIPT_PATH" ]]; then
  echo "[error] crop script not found: $CROP_SCRIPT_PATH" >&2
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
failed=0
thumbnails_to_copy=()

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

  if output="$($PYTHON_BIN "$SCRIPT_PATH" \
    --template "$TEMPLATE_PATH" \
    --source-docx "$src" \
    --input "$txt" \
    --output "$out" 2>&1)"; then
    generated_path="${out%.docx}_al.docx"
    echo "[created] $(basename "$generated_path")"
    ((processed+=1))

    while IFS= read -r thumb; do
      thumb="${thumb#THUMBNAIL:}"
      thumb="${thumb# }"
      thumb="$(printf '%s' "$thumb" | sed -E 's/[[:space:]]*\*+[[:space:]]*$//')"
      [[ -z "$thumb" ]] && continue
      thumbnails_to_copy+=("$thumb")
    done < <(grep -E '^THUMBNAIL:' "$txt" || true)
  else
    ((failed+=1))
    printf '%s\n' "$output" >&2
  fi
done

crop_failed=0
if crop_output="$($PYTHON_BIN "$CROP_SCRIPT_PATH" "$TARGET_DIR" 2>&1)"; then
  while IFS= read -r line; do
    [[ -z "$line" ]] && continue
    cleaned="$line"
    cleaned="${cleaned#\[wrote\] }"
    cleaned="${cleaned#${TARGET_DIR%/}/}"
    echo "[cropped] $cleaned"
  done <<< "$crop_output"
else
  crop_failed=1
  while IFS= read -r line; do
    [[ -z "$line" ]] && continue
    echo "[cropped] $line" >&2
  done <<< "$crop_output"
fi

copied_png=0
if [[ ${#thumbnails_to_copy[@]} -gt 0 ]]; then
  declare -A seen=()
  for thumb in "${thumbnails_to_copy[@]}"; do
    [[ -n "${seen[$thumb]+x}" ]] && continue
    seen[$thumb]=1
    src_png="${TARGET_DIR%/}/$thumb"
    if [[ ! -f "$src_png" ]]; then
      continue
    fi
    dest_png="${OUTPUT_DIR}/$(basename "$thumb")"
    cp -f -- "$src_png" "$dest_png"
    echo "[copied] $(basename "$thumb")"
    ((copied_png+=1))
  done
fi

echo "[done] generated: $processed, skipped: $skipped, copied png: $copied_png, failed: $failed, crop_failed: $crop_failed"
if (( failed > 0 )); then
  exit 1
fi
if (( crop_failed > 0 )); then
  exit 1
fi
