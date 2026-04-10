#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "$0")/.." && pwd)"

cd "$ROOT_DIR"

go test ./...
go test -tags gui ./...
./scripts/parity_check.sh
python3 -m unittest discover -s ./python/tests -p 'test_*.py'
python3 -m py_compile ./python/content_list_core.py ./python/content_list_generator.py ./scripts/copy_email_files.py

echo "All checks passed."
