#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "$0")" && pwd)"
BUILD_DIR="$ROOT_DIR/build"

mkdir -p "$BUILD_DIR"
cd "$ROOT_DIR"

go build -tags gui -o "$BUILD_DIR/content-list-generator-gui" .
exec "$BUILD_DIR/content-list-generator-gui" --gui "$@"
