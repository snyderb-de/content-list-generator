#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "$0")/.." && pwd)"

cd "$ROOT_DIR"

echo "Running Go parity checks against shared fixtures..."
go test ./... -run 'TestRunScanMatchesGoldenFixture|TestCopyEmailFilesMatchesGoldenFixture' -count=1

# Python parity tests live in python/tests/. They are currently gitignored,
# so clean checkouts (CI) won't have them. Skip gracefully when absent;
# tracked checkouts still run them locally.
if [ -f "$ROOT_DIR/python/tests/test_content_scan.py" ] && [ -f "$ROOT_DIR/python/tests/test_email_copy.py" ]; then
  echo "Running Python parity checks against shared fixtures..."
  python3 -m unittest \
    python.tests.test_content_scan.ContentScanTests.test_run_scan_matches_golden_fixture \
    python.tests.test_email_copy.EmailCopyTests.test_copy_email_matches_golden_fixture
else
  echo "Skipping Python parity checks — python/tests/ not present in this checkout."
fi

echo "Parity checks passed."
