#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "$0")/.." && pwd)"
MODE="${1:-go}"
BUILD_DIR="$ROOT_DIR/build"

cd "$ROOT_DIR"

case "$MODE" in
  go)
    mkdir -p "$BUILD_DIR"
    go build -o "$BUILD_DIR/content-list-generator" .
    exec "$BUILD_DIR/content-list-generator"
    ;;
  go-gui)
    mkdir -p "$BUILD_DIR"
    go build -tags gui -o "$BUILD_DIR/content-list-generator-gui" .
    exec "$BUILD_DIR/content-list-generator-gui" --gui
    ;;
  python|python-gui)
    exec python3 ./python/content_list_generator.py
    ;;
  python-cli)
    shift || true
    exec python3 ./python/content_list_generator.py --cli "$@"
    ;;
  *)
    echo "Usage: $0 [go|go-gui|python|python-cli]" >&2
    exit 1
    ;;
esac
