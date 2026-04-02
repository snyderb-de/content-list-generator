#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "$0")" && pwd)"

mkdir -p "$ROOT_DIR/bin"
cd "$ROOT_DIR"

go build -tags gui -o "$ROOT_DIR/bin/content-list-generator-gui" .
exec "$ROOT_DIR/bin/content-list-generator-gui" --gui "$@"
