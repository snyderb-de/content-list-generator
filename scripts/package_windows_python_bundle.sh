#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "$0")/.." && pwd)"
OUT_DIR="$ROOT_DIR/dist/smoke/windows-python"
ARCHIVE="$ROOT_DIR/dist/content-list-generator-windows-python-smoke.zip"

rm -rf "$OUT_DIR"
mkdir -p "$OUT_DIR/python" "$OUT_DIR/scripts"

cd "$ROOT_DIR"

./scripts/parity_check.sh
python3 -m unittest discover -s ./python -p 'test_*.py'
python3 -m py_compile ./python/content_list_core.py ./python/content_list_generator.py ./scripts/copy_email_files.py

cp python/content_list_core.py "$OUT_DIR/python/"
cp python/content_list_generator.py "$OUT_DIR/python/"
cp scripts/copy_email_files.py "$OUT_DIR/scripts/"
cp README.md "$OUT_DIR/"
cp SMOKE_TEST_PLAN.md "$OUT_DIR/"

cat > "$OUT_DIR/run-content-list-generator.cmd" <<'EOF'
@echo off
setlocal
python "%~dp0python\content_list_generator.py"
EOF

cat > "$OUT_DIR/run-email-copy.cmd" <<'EOF'
@echo off
setlocal
python "%~dp0scripts\copy_email_files.py"
EOF

cat > "$OUT_DIR/run-content-list-generator-cli.cmd" <<'EOF'
@echo off
setlocal
python "%~dp0python\content_list_generator.py" --cli %*
EOF

python3 - <<'PY'
from pathlib import Path
import zipfile

root = Path("dist/smoke/windows-python")
archive = Path("dist/content-list-generator-windows-python-smoke.zip")
with zipfile.ZipFile(archive, "w", compression=zipfile.ZIP_DEFLATED) as zf:
    for path in sorted(root.rglob("*")):
        if path.is_file():
            zf.write(path, path.relative_to(root))
PY

echo "Built Windows Python smoke bundle:"
echo "  $ARCHIVE"
