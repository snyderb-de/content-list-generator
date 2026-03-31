#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "$0")/.." && pwd)"
MODE="${1:-go}"

cd "$ROOT_DIR"

case "$MODE" in
  go)
    mkdir -p ./bin
    go build -o ./bin/content-list-generator .
    exec ./bin/content-list-generator
    ;;
  python|python-gui)
    exec python3 ./python/content_list_generator.py
    ;;
  python-cli)
    shift || true
    exec python3 ./python/content_list_generator.py --cli "$@"
    ;;
  *)
    echo "Usage: $0 [go|python|python-cli]" >&2
    exit 1
    ;;
esac
