#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "$0")/.." && pwd)"

cd "$ROOT_DIR"

echo "Running Go parity checks against shared fixtures..."
go test ./... -run 'TestRunScanMatchesGoldenFixture|TestCopyEmailFilesMatchesGoldenFixture' -count=1

echo "Running Python parity checks against shared fixtures..."
python3 -m unittest \
  python.test_content_list_generator.ContentListGeneratorTests.test_run_scan_matches_golden_fixture \
  python.test_content_list_generator.ContentListGeneratorTests.test_copy_email_matches_golden_fixture

echo "Parity checks passed."
