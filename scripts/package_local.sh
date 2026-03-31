#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "$0")/.." && pwd)"
DIST_DIR="$ROOT_DIR/dist/local"
PY_DIR="$DIST_DIR/python-app"

mkdir -p "$ROOT_DIR/bin" "$DIST_DIR" "$PY_DIR"

cd "$ROOT_DIR"

./scripts/dev_check.sh

go build -o "$ROOT_DIR/bin/content-list-generator" .

rm -rf "$PY_DIR"
mkdir -p "$PY_DIR/python" "$PY_DIR/scripts"
cp "$ROOT_DIR/python/content_list_core.py" "$PY_DIR/python/"
cp "$ROOT_DIR/python/content_list_generator.py" "$PY_DIR/python/"
cp "$ROOT_DIR/scripts/copy_email_files.py" "$PY_DIR/scripts/"
cp "$ROOT_DIR/README.md" "$PY_DIR/"

cat > "$PY_DIR/run-python-app.sh" <<'EOF'
#!/usr/bin/env bash
set -euo pipefail
DIR="$(cd "$(dirname "$0")" && pwd)"
exec python3 "$DIR/python/content_list_generator.py" "$@"
EOF
chmod +x "$PY_DIR/run-python-app.sh"

tar -czf "$DIST_DIR/content-list-generator-python-app.tar.gz" -C "$DIST_DIR" python-app

echo "Built local artifacts:"
echo "  Go binary: $ROOT_DIR/bin/content-list-generator"
echo "  Python bundle: $DIST_DIR/content-list-generator-python-app.tar.gz"
