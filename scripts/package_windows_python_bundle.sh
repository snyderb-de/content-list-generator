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
mkdir -p "$OUT_DIR/scripts"
rm -f "$ARCHIVE" "$TMP_ARCHIVE"

cd "$ROOT_DIR"

./scripts/parity_check.sh
python3 -m unittest discover -s ./python -p 'test_*.py'
python3 -m py_compile ./python/content_list_core.py ./python/content_list_generator.py ./scripts/copy_email_files.py

cp python/content_list_core.py "$OUT_DIR/scripts/"
cp python/content_list_generator.py "$OUT_DIR/scripts/"
cp scripts/copy_email_files.py "$OUT_DIR/scripts/"
cp README.md "$OUT_DIR/"
cp INSTALL.md "$OUT_DIR/"
cp SMOKE_TEST_PLAN.md "$OUT_DIR/"
cp requirements.txt "$OUT_DIR/"

cat > "$OUT_DIR/run-content-list-generator.cmd" <<'EOF'
@echo off
setlocal
set "SCRIPT=%USERPROFILE%\scripts\content-list-gen\content_list_generator.py"
if not exist "%SCRIPT%" set "SCRIPT=%USERPROFILE%\scripts\content_list_generator.py"
if not exist "%SCRIPT%" set "SCRIPT=%~dp0scripts\content_list_generator.py"
python "%SCRIPT%"
EOF

cat > "$OUT_DIR/content-list-generator.bat" <<'EOF'
@echo off

REM ---------------------------------------------------------------------------
REM  Content List Generator - GUI Launcher
REM  Requires: Python 3.x, tkinter, customtkinter
REM  Install deps (run once): pip install -r requirements.txt
REM
REM  Preferred deploy target:
REM    %USERPROFILE%\scripts\content-list-gen\
REM ---------------------------------------------------------------------------

set "SCRIPT=%USERPROFILE%\scripts\content-list-gen\content_list_generator.py"
if not exist "%SCRIPT%" set "SCRIPT=%USERPROFILE%\scripts\content_list_generator.py"
if not exist "%SCRIPT%" set "SCRIPT=%~dp0scripts\content_list_generator.py"

if not exist "%SCRIPT%" (
    echo.
    echo ERROR: could not find content_list_generator.py.
    echo Looked for:
    echo   %USERPROFILE%\scripts\content-list-gen\content_list_generator.py
    echo   %USERPROFILE%\scripts\content_list_generator.py
    echo   %~dp0scripts\content_list_generator.py
    echo.
    pause
    exit /b 1
)

python "%SCRIPT%" %*

REM If Python exits with an error (e.g. missing dependency), hold the window
REM open so the user can read the message before it disappears.
if %errorlevel% neq 0 (
    echo.
    echo ERROR: the script exited with code %errorlevel%.
    echo Check that Python is installed and dependencies are up to date:
    echo   pip install -r requirements.txt
    echo.
    pause
)
EOF

cat > "$OUT_DIR/launch-content-list-generator-gui.bat" <<'EOF'
@echo off
call "%~dp0content-list-generator.bat" %*
exit /b %errorlevel%
EOF

cat > "$OUT_DIR/run-content-list-generator.bat" <<'EOF'
@echo off
call "%~dp0content-list-generator.bat" %*
exit /b %errorlevel%
EOF

cat > "$OUT_DIR/run-email-copy.cmd" <<'EOF'
@echo off
setlocal
set "SCRIPT=%USERPROFILE%\scripts\content-list-gen\copy_email_files.py"
if not exist "%SCRIPT%" set "SCRIPT=%USERPROFILE%\scripts\copy_email_files.py"
if not exist "%SCRIPT%" set "SCRIPT=%~dp0scripts\copy_email_files.py"
python "%SCRIPT%"
EOF

cat > "$OUT_DIR/run-content-list-generator-cli.cmd" <<'EOF'
@echo off
setlocal
set "SCRIPT=%USERPROFILE%\scripts\content-list-gen\content_list_generator.py"
if not exist "%SCRIPT%" set "SCRIPT=%USERPROFILE%\scripts\content_list_generator.py"
if not exist "%SCRIPT%" set "SCRIPT=%~dp0scripts\content_list_generator.py"
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
