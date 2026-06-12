#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "$0")/../.." && pwd)"

cd "$ROOT_DIR"

go test ./... -run 'TestCopyEmailFiles' -count=1
python3 -m unittest python.tests.test_email_copy
