#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "$0")/.." && pwd)"
OUT_DIR="$ROOT_DIR/releases/windows-python"
BUILD_DIR="$ROOT_DIR/build"
ARCHIVE="$OUT_DIR/content-list-generator-windows-python.zip"
TMP_ARCHIVE="$BUILD_DIR/content-list-generator-windows-python.zip"

mkdir -p "$OUT_DIR" "$BUILD_DIR"
find "$OUT_DIR" -mindepth 1 -maxdepth 1 \
  ! -name '.gitkeep' \
  -exec rm -rf {} +
rm -f "$ARCHIVE" "$TMP_ARCHIVE"

cd "$ROOT_DIR"

./scripts/parity_check.sh
python3 -m unittest discover -s ./python -p 'test_*.py'
python3 -m py_compile ./python/content_list_core.py ./python/content_list_generator.py

cp python/content_list_core.py "$OUT_DIR/"
cp python/content_list_generator.py "$OUT_DIR/"
cp README.md "$OUT_DIR/"
cp INSTALL.md "$OUT_DIR/"
cp SMOKE_TEST_PLAN.md "$OUT_DIR/"
cp requirements.txt "$OUT_DIR/"

cat > "$OUT_DIR/run-content-list-generator.cmd" <<'EOF'
@echo off
setlocal
set "SCRIPT=%USERPROFILE%\scripts\content_list_generator.py"
if not exist "%SCRIPT%" set "SCRIPT=%~dp0content_list_generator.py"
python "%SCRIPT%"
EOF

cat > "$OUT_DIR/run-content-list-generator.bat" <<'EOF'
@echo off
setlocal
set "SCRIPT=%USERPROFILE%\scripts\content_list_generator.py"
if not exist "%SCRIPT%" set "SCRIPT=%~dp0content_list_generator.py"

if not exist "%SCRIPT%" (
  echo Could not find content_list_generator.py.
  echo Expected location:
  echo   %USERPROFILE%\scripts\content_list_generator.py
  echo.
  echo Copy these files into %USERPROFILE%\scripts\:
  echo   content_list_generator.py
  echo   content_list_core.py
  exit /b 1
)

where py >nul 2>&1
if %ERRORLEVEL%==0 (
  py -3 "%SCRIPT%" %*
  exit /b %ERRORLEVEL%
)

where python >nul 2>&1
if %ERRORLEVEL%==0 (
  python "%SCRIPT%" %*
  exit /b %ERRORLEVEL%
)

echo Python 3 was not found on this system.
echo Install Python 3, then run this launcher again.
exit /b 1
EOF

cat > "$OUT_DIR/run-email-copy.cmd" <<'EOF'
@echo off
setlocal
set "SCRIPT=%USERPROFILE%\scripts\content_list_generator.py"
if not exist "%SCRIPT%" set "SCRIPT=%~dp0content_list_generator.py"
python "%SCRIPT%" --mode email-copy %*
EOF

cat > "$OUT_DIR/run-content-list-generator-cli.cmd" <<'EOF'
@echo off
setlocal
set "SCRIPT=%USERPROFILE%\scripts\content_list_generator.py"
if not exist "%SCRIPT%" set "SCRIPT=%~dp0content_list_generator.py"
python "%SCRIPT%" --cli %*
EOF

python3 - <<'PY'
from pathlib import Path
import zipfile

root = Path("releases/windows-python")
archive = Path("build/content-list-generator-windows-python.zip")
with zipfile.ZipFile(archive, "w", compression=zipfile.ZIP_DEFLATED) as zf:
    for path in sorted(root.rglob("*")):
        if path.is_file():
            zf.write(path, path.relative_to(root))
PY
mv "$TMP_ARCHIVE" "$ARCHIVE"

echo "Built Windows Python package:"
echo "  $ARCHIVE"
