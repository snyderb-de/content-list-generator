#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "$0")/.." && pwd)"
OUT_DIR="$ROOT_DIR/dist/smoke/macos"
ARCHIVE="$ROOT_DIR/dist/content-list-generator-macos-local.tar.gz"

if [[ "$(uname -s)" != "Darwin" ]]; then
  echo "This helper is intended to run on macOS." >&2
  exit 1
fi

rm -rf "$OUT_DIR"
mkdir -p "$OUT_DIR"

cd "$ROOT_DIR"

./scripts/dev_check.sh

go build -o "$OUT_DIR/content-list-generator-tui" .
go build -tags gui -o "$OUT_DIR/content-list-generator-gui" .
cp README.md "$OUT_DIR/"
cp INSTALL.md "$OUT_DIR/"
cp SMOKE_TEST_PLAN.md "$OUT_DIR/"

cat > "$OUT_DIR/README-LOCAL.txt" <<'EOF'
Local macOS smoke bundle

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

tar -czf "$ARCHIVE" -C "$OUT_DIR" .
echo "Built macOS local smoke bundle:"
echo "  $ARCHIVE"
