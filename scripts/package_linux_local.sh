#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "$0")/.." && pwd)"
OUT_DIR="$ROOT_DIR/releases/linux"
BUILD_DIR="$ROOT_DIR/build"
ARCHIVE="$OUT_DIR/content-list-generator-linux.tar.gz"
TMP_ARCHIVE="$BUILD_DIR/content-list-generator-linux.tar.gz"

if [[ "$(uname -s)" != "Linux" ]]; then
  echo "This helper is intended to run on Linux." >&2
  exit 1
fi

mkdir -p "$OUT_DIR" "$BUILD_DIR"
find "$OUT_DIR" -mindepth 1 -maxdepth 1 \
  ! -name '.gitkeep' \
  -exec rm -rf {} +
rm -f "$ARCHIVE" "$TMP_ARCHIVE"

cd "$ROOT_DIR"

./scripts/dev_check.sh

go build -o "$OUT_DIR/content-list-generator-tui" .
go build -tags gui -o "$OUT_DIR/content-list-generator-gui" .
cp README.md "$OUT_DIR/"
cp INSTALL.md "$OUT_DIR/"
cp SMOKE_TEST_PLAN.md "$OUT_DIR/"

cat > "$OUT_DIR/README-PACKAGE.txt" <<'EOF'
Local Linux package

Included:
- content-list-generator-gui
- content-list-generator-tui
- README.md
- SMOKE_TEST_PLAN.md

Launch the GUI:
./content-list-generator-gui --gui

Launch the TUI:
./content-list-generator-tui
EOF

cat > "$OUT_DIR/run-content-list-generator-gui.sh" <<'EOF'
#!/usr/bin/env bash
set -euo pipefail
DIR="$(cd "$(dirname "$0")" && pwd)"
exec "$DIR/content-list-generator-gui" --gui "$@"
EOF

cat > "$OUT_DIR/run-content-list-generator-tui.sh" <<'EOF'
#!/usr/bin/env bash
set -euo pipefail
DIR="$(cd "$(dirname "$0")" && pwd)"
exec "$DIR/content-list-generator-tui" "$@"
EOF

chmod +x \
  "$OUT_DIR/content-list-generator-tui" \
  "$OUT_DIR/content-list-generator-gui" \
  "$OUT_DIR/run-content-list-generator-gui.sh" \
  "$OUT_DIR/run-content-list-generator-tui.sh"

tar -czf "$TMP_ARCHIVE" -C "$OUT_DIR" .
mv "$TMP_ARCHIVE" "$ARCHIVE"
echo "Built Linux package:"
echo "  $ARCHIVE"
