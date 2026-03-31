#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "$0")/.." && pwd)"
OUT_DIR="$ROOT_DIR/dist/smoke/linux"
ARCHIVE="$ROOT_DIR/dist/content-list-generator-linux-local.tar.gz"

if [[ "$(uname -s)" != "Linux" ]]; then
  echo "This helper is intended to run on Linux." >&2
  exit 1
fi

rm -rf "$OUT_DIR"
mkdir -p "$OUT_DIR"

cd "$ROOT_DIR"

./scripts/dev_check.sh

go build -o "$OUT_DIR/content-list-generator-tui" .
go build -tags gui -o "$OUT_DIR/content-list-generator-gui" .
cp README.md "$OUT_DIR/"
cp SMOKE_TEST_PLAN.md "$OUT_DIR/"

cat > "$OUT_DIR/README-LOCAL.txt" <<'EOF'
Local Linux smoke bundle

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

tar -czf "$ARCHIVE" -C "$OUT_DIR" .
echo "Built Linux local smoke bundle:"
echo "  $ARCHIVE"
