#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "$0")/.." && pwd)"
BUILD_DIR="$ROOT_DIR/build"
LOCAL_DIR="$BUILD_DIR/local"
PY_DIR="$LOCAL_DIR/python-app"

mkdir -p "$BUILD_DIR" "$LOCAL_DIR" "$PY_DIR"

cd "$ROOT_DIR"

./scripts/dev_check.sh

go build -o "$BUILD_DIR/content-list-generator" .

if go build -tags gui -o "$BUILD_DIR/content-list-generator-gui" .; then
  echo "  Go GUI binary: $BUILD_DIR/content-list-generator-gui"
else
  echo "  Go GUI binary: skipped"
fi

rm -rf "$PY_DIR"
mkdir -p "$PY_DIR/python" "$PY_DIR/scripts"
cp "$ROOT_DIR/python/content_list_core.py" "$PY_DIR/python/"
cp "$ROOT_DIR/python/content_list_generator.py" "$PY_DIR/python/"
cp "$ROOT_DIR/scripts/copy_email_files.py" "$PY_DIR/scripts/"
cp "$ROOT_DIR/README.md" "$PY_DIR/"
cp "$ROOT_DIR/requirements.txt" "$PY_DIR/"

cat > "$PY_DIR/run-python-app.sh" <<'EOF'
#!/usr/bin/env bash
set -euo pipefail
DIR="$(cd "$(dirname "$0")" && pwd)"
exec python3 "$DIR/python/content_list_generator.py" "$@"
EOF
chmod +x "$PY_DIR/run-python-app.sh"

tar -czf "$LOCAL_DIR/content-list-generator-python-app.tar.gz" -C "$LOCAL_DIR" python-app

echo "Built local artifacts:"
echo "  Go binary: $BUILD_DIR/content-list-generator"
echo "  Python bundle: $LOCAL_DIR/content-list-generator-python-app.tar.gz"
