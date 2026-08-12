# File Creation and Modification Dates Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Append best-effort file creation and modification timestamps to standard content-list CSV/XLSX output in both Go and Python runtimes.

**Architecture:** Capture timestamp metadata during the filesystem stat already performed by each scanner, format it through one runtime-level helper, and append it to standard rows after `Hash Value`. Go isolates creation-time extraction in build-tagged OS files; Python uses `st_birthtime`, Windows `st_ctime`, or an unavailable fallback. Existing specialized schemas and the first seven standard columns remain unchanged.

**Tech Stack:** Go 1.26, Python 3.12, standard-library filesystem metadata, `encoding/csv`, Python `csv`, Excelize, Python ZIP-based XLSX writer, `unittest`.

## Global Constraints

- Standard headers are exactly `Date Created` and `Date Modified`, appended after `Hash Value` in that order.
- Timestamp values use local scan-machine time in exactly `YYYY-MM-DD HH:MM:SS ±HH:MM` format.
- An unavailable, zero, invalid, or out-of-range timestamp is exactly `unknown`.
- Windows creation time uses the native file creation timestamp; macOS uses filesystem birth time; unsupported Linux/filesystem creation time is `unknown`.
- Agency-template, folders-only, email-manifest, and clone-difference schemas do not change.
- No new production dependency is introduced.
- The canonical Python runtime and `deploy/windows/scripts/content-list-gen/content_list_core.py` remain byte-for-byte aligned.

## File Map

- Create `file_timestamp.go`: shared constants and timestamp formatter.
- Create `file_timestamp_darwin.go`: macOS birth-time extraction.
- Create `file_timestamp_windows.go`: Windows creation-time extraction.
- Create `file_timestamp_other.go`: unsupported-platform fallback.
- Create `file_timestamp_test.go`: platform-neutral Go formatter tests.
- Modify `core.go`: extend standard headers/work items and append timestamp fields.
- Modify `scan_test.go`: standard output, XLSX, agency-schema, clone compatibility, and golden fixture assertions.
- Modify `testing/content-scan/generate_fixture.py`: assign fixed modification times and generate timestamp expectation markers.
- Modify `testing/content-scan/fixtures/expected-scan-hash.csv`: add both timestamp columns and markers.
- Modify `python/content_list_core.py`: Python timestamp extraction/formatting and row emission.
- Modify `deploy/windows/scripts/content-list-gen/content_list_core.py`: mirror the canonical Python runtime.
- Modify `python/tests/test_content_scan.py`: Python formatter, output, XLSX, schema, clone, and fixture assertions.
- Modify `project-dashboard/user-manual.html`: document both columns and creation-time caveat.

---

### Task 1: Go Timestamp Metadata and Standard Output

**Files:**
- Create: `file_timestamp.go`
- Create: `file_timestamp_darwin.go`
- Create: `file_timestamp_windows.go`
- Create: `file_timestamp_other.go`
- Create: `file_timestamp_test.go`
- Modify: `core.go:110-130,262-270,700-790`
- Modify: `scan_test.go:1-170,252-350,390-430`
- Modify: `testing/content-scan/generate_fixture.py`
- Modify: `testing/content-scan/fixtures/expected-scan-hash.csv`

**Interfaces:**
- Produces: `formatFileTimestamp(value time.Time, available bool) string`.
- Produces: `fileCreationTime(info os.FileInfo) (time.Time, bool)` with one build-tagged implementation selected per target OS.
- Produces: `scanWork.dateCreated string` and `scanWork.dateModified string` for standard report rows.
- Preserves: standard columns 0-6 and every specialized schema.

- [ ] **Step 1: Add failing formatter and creation-fallback tests**

Create `file_timestamp_test.go`:

```go
package main

import (
	"testing"
	"time"
)

func TestFormatFileTimestamp(t *testing.T) {
	previousLocal := time.Local
	time.Local = time.FixedZone("EDT", -4*60*60)
	t.Cleanup(func() { time.Local = previousLocal })
	value := time.Date(2026, 8, 12, 19, 42, 7, 900_000_000, time.UTC)
	if got := formatFileTimestamp(value, true); got != "2026-08-12 15:42:07 -04:00" {
		t.Fatalf("unexpected timestamp: %q", got)
	}
}

func TestFormatFileTimestampUnknown(t *testing.T) {
	for _, tc := range []struct {
		name      string
		value     time.Time
		available bool
	}{
		{name: "unavailable", value: time.Now(), available: false},
		{name: "zero", value: time.Time{}, available: true},
		{name: "out of range", value: time.Date(10000, 1, 1, 0, 0, 0, 0, time.UTC), available: true},
	} {
		t.Run(tc.name, func(t *testing.T) {
			if got := formatFileTimestamp(tc.value, tc.available); got != "unknown" {
				t.Fatalf("got %q want unknown", got)
			}
		})
	}
}
```

- [ ] **Step 2: Run the focused Go test and verify it fails**

Run:

```bash
go test ./... -run 'TestFormatFileTimestamp' -count=1
```

Expected: compilation fails because `formatFileTimestamp` is undefined.

- [ ] **Step 3: Implement the shared formatter**

Create `file_timestamp.go`:

```go
package main

import "time"

const (
	fileTimestampLayout = "2006-01-02 15:04:05 -07:00"
	unknownFileTimestamp = "unknown"
)

func formatFileTimestamp(value time.Time, available bool) string {
	if !available || value.IsZero() {
		return unknownFileTimestamp
	}
	localValue := value.Local()
	if localValue.Year() < 1 || localValue.Year() > 9999 {
		return unknownFileTimestamp
	}
	return localValue.Format(fileTimestampLayout)
}
```

- [ ] **Step 4: Add platform-specific creation-time helpers**

Create `file_timestamp_darwin.go`:

```go
//go:build darwin

package main

import (
	"os"
	"syscall"
	"time"
)

func fileCreationTime(info os.FileInfo) (time.Time, bool) {
	stat, ok := info.Sys().(*syscall.Stat_t)
	if !ok || stat.Birthtimespec.Sec <= 0 {
		return time.Time{}, false
	}
	return time.Unix(stat.Birthtimespec.Sec, stat.Birthtimespec.Nsec), true
}
```

Create `file_timestamp_windows.go`:

```go
//go:build windows

package main

import (
	"os"
	"syscall"
	"time"
)

func fileCreationTime(info os.FileInfo) (time.Time, bool) {
	data, ok := info.Sys().(*syscall.Win32FileAttributeData)
	if !ok {
		return time.Time{}, false
	}
	nanoseconds := data.CreationTime.Nanoseconds()
	if nanoseconds <= 0 {
		return time.Time{}, false
	}
	return time.Unix(0, nanoseconds), true
}
```

Create `file_timestamp_other.go`:

```go
//go:build !darwin && !windows

package main

import (
	"os"
	"time"
)

func fileCreationTime(os.FileInfo) (time.Time, bool) {
	return time.Time{}, false
}
```

- [ ] **Step 5: Run formatter tests and cross-compile the platform helpers**

Run:

```bash
go test ./... -run 'TestFormatFileTimestamp' -count=1
GOOS=windows GOARCH=amd64 go build ./...
GOOS=linux GOARCH=amd64 go build ./...
```

Expected: all commands pass. Cross-platform commands compile the selected platform helper without executing foreign binaries.

- [ ] **Step 6: Add failing standard-output and XLSX assertions**

In `TestRunScanWritesCSVAndHashes`, set a known modification time after writing fixtures:

```go
fixedModified := time.Date(2024, 5, 1, 12, 34, 56, 0, time.Local)
for _, path := range []string{
	filepath.Join(source, "a.txt"),
	filepath.Join(source, "nested", "b.bin"),
} {
	if err := os.Chtimes(path, fixedModified, fixedModified); err != nil {
		t.Fatalf("set fixture timestamps: %v", err)
	}
}
```

Assert the full header and timestamp contract:

```go
expectedHeaders := []string{
	"File Name", "Extension", "Size in Bytes", "Size in Human Readable",
	"Path From Root Folder", "Hash Algorithm", "Hash Value",
	"Date Created", "Date Modified",
}
assertRowsEqual(t, [][]string{rows[0]}, [][]string{expectedHeaders})
assertFileTimestampValue(t, rows[1][7], true)
if rows[1][8] != formatFileTimestamp(fixedModified, true) {
	t.Fatalf("unexpected modified timestamp: %q", rows[1][8])
}
```

Add this test helper in `scan_test.go`:

```go
func assertFileTimestampValue(t *testing.T, value string, allowUnknown bool) {
	t.Helper()
	if allowUnknown && value == unknownFileTimestamp {
		return
	}
	if _, err := time.Parse(fileTimestampLayout, value); err != nil {
		t.Fatalf("invalid file timestamp %q: %v", value, err)
	}
}
```

Extend `TestRunScanCreatesXLSX` to assert `H1`, `I1`, `H2`, and `I2` contain the new headers and timestamp strings. Keep `TestRunScanWritesAgencyTemplate`'s exact 31-column header assertion unchanged and add `len(rows[1]) == len(expectedHeaders)`.

- [ ] **Step 7: Run the focused scan tests and verify they fail**

Run:

```bash
go test ./... -run 'TestRunScanWritesCSVAndHashes|TestRunScanCreatesXLSX|TestRunScanWritesAgencyTemplate' -count=1
```

Expected: standard header and XLSX timestamp assertions fail because rows still contain seven columns; the agency assertion continues to pass.

- [ ] **Step 8: Carry timestamps through Go scan work and append standard fields**

Add fields to `scanWork` in `core.go`:

```go
dateCreated  string
dateModified string
```

Append headers to `standardReportHeaders`:

```go
"Date Created",
"Date Modified",
```

After `d.Info()` succeeds, extract metadata once:

```go
createdAt, createdAvailable := fileCreationTime(info)
modifiedAt := info.ModTime()
```

Populate the work item:

```go
dateCreated:  formatFileTimestamp(createdAt, createdAvailable),
dateModified: formatFileTimestamp(modifiedAt, !modifiedAt.IsZero()),
```

Append to only the standard row before the existing agency-template override:

```go
ready.work.dateCreated,
ready.work.dateModified,
```

- [ ] **Step 9: Make the shared fixture timestamp-aware**

In `testing/content-scan/generate_fixture.py`, add `import os`, define `FIXED_MODIFIED_EPOCH = 1_714_566_896`, call `os.utime(target, (FIXED_MODIFIED_EPOCH, FIXED_MODIFIED_EPOCH))` for each source file, append both headers, and write these markers in each expected row:

```python
"<native-or-unknown>",
"<fixed-modified>",
```

Regenerate `testing/content-scan/fixtures/expected-scan-hash.csv`:

```bash
python3 testing/content-scan/generate_fixture.py
```

In `TestRunScanMatchesGoldenFixture`, reset every kept fixture file with `os.Chtimes(path, fixed, fixed)` before scanning. Compare normal cells literally; for `<native-or-unknown>`, call `assertFileTimestampValue(..., true)`; for `<fixed-modified>`, compare with `formatFileTimestamp(fixed, true)`.

- [ ] **Step 10: Run all Go tests**

Run:

```bash
go test ./... -count=1
```

Expected: all Go tests pass, including existing clone comparison tests that now consume nine-column scan files through their unchanged first-seven-column parser.

- [ ] **Step 11: Commit the Go slice**

```bash
git add file_timestamp.go file_timestamp_darwin.go file_timestamp_windows.go file_timestamp_other.go file_timestamp_test.go core.go scan_test.go testing/content-scan/generate_fixture.py testing/content-scan/fixtures/expected-scan-hash.csv
git commit -m "feat: add file timestamps to Go content lists"
```

---

### Task 2: Python Runtime Parity and Deployment Copy

**Files:**
- Modify: `python/content_list_core.py:1-110,549-590,910-1010`
- Modify: `deploy/windows/scripts/content-list-gen/content_list_core.py` at the same sections
- Modify: `python/tests/test_content_scan.py:1-210`

**Interfaces:**
- Produces: `format_file_timestamp(value: float | None) -> str`.
- Produces: `file_creation_timestamp(stat_result: os.stat_result) -> float | None`.
- Changes: `iter_scan_files(...)` yields `(Path, int, str, str, str)` for path, size, relative path, formatted creation time, and formatted modification time.
- Consumes: shared fixture markers `<native-or-unknown>` and `<fixed-modified>` from Task 1.

- [ ] **Step 1: Add failing Python formatter tests**

Add imports and tests to `python/tests/test_content_scan.py`:

```python
from datetime import datetime
from types import SimpleNamespace

def test_format_file_timestamp(self) -> None:
    value = 1_723_490_527.9
    expected = datetime.fromtimestamp(value).astimezone().isoformat(sep=" ", timespec="seconds")
    self.assertEqual(core.format_file_timestamp(value), expected)

def test_format_file_timestamp_unknown(self) -> None:
    self.assertEqual(core.format_file_timestamp(None), "unknown")
    self.assertEqual(core.file_creation_timestamp(SimpleNamespace()), None)
```

- [ ] **Step 2: Run the focused Python tests and verify they fail**

Run with the project environment:

```bash
.venv/bin/python -m unittest \
  python.tests.test_content_scan.ContentScanTests.test_format_file_timestamp \
  python.tests.test_content_scan.ContentScanTests.test_format_file_timestamp_unknown
```

Expected: errors because both helper functions are undefined.

- [ ] **Step 3: Implement Python timestamp helpers**

Add `from datetime import datetime` and these helpers to `python/content_list_core.py`:

```python
UNKNOWN_FILE_TIMESTAMP = "unknown"


def format_file_timestamp(value: float | None) -> str:
    if value is None:
        return UNKNOWN_FILE_TIMESTAMP
    try:
        return datetime.fromtimestamp(value).astimezone().isoformat(sep=" ", timespec="seconds")
    except (OSError, OverflowError, ValueError):
        return UNKNOWN_FILE_TIMESTAMP


def file_creation_timestamp(stat_result: os.stat_result) -> float | None:
    birth_time = getattr(stat_result, "st_birthtime", None)
    if birth_time is not None:
        return float(birth_time)
    if os.name == "nt":
        windows_creation_time = getattr(stat_result, "st_ctime", None)
        return float(windows_creation_time) if windows_creation_time is not None else None
    return None
```

- [ ] **Step 4: Run formatter tests and verify they pass**

Run the command from Step 2.

Expected: both tests pass.

- [ ] **Step 5: Add failing Python standard-output, XLSX, and agency assertions**

In `test_run_scan_creates_xlsx_and_hashes`, set a known mtime with `os.utime`, then assert:

```python
self.assertEqual(rows[0], core.REPORT_HEADERS)
self.assertEqual(rows[0][-2:], ["Date Created", "Date Modified"])
self.assert_file_timestamp(rows[1][7], allow_unknown=True)
self.assertEqual(rows[1][8], core.format_file_timestamp(fixed_modified_epoch))
```

Add this method to `ContentScanTests`:

```python
def assert_file_timestamp(self, value: str, *, allow_unknown: bool) -> None:
    if allow_unknown and value == core.UNKNOWN_FILE_TIMESTAMP:
        return
    parsed = datetime.fromisoformat(value)
    self.assertIsNotNone(parsed.utcoffset())
```

Open the produced XLSX ZIP and assert the sheet XML contains `Date Created`, `Date Modified`, and the expected formatted modification timestamp. In `test_run_scan_writes_agency_template`, assert both header and data row lengths still equal 31.

- [ ] **Step 6: Run the focused scan tests and verify they fail**

Run:

```bash
.venv/bin/python -m unittest \
  python.tests.test_content_scan.ContentScanTests.test_run_scan_creates_xlsx_and_hashes \
  python.tests.test_content_scan.ContentScanTests.test_run_scan_writes_agency_template
```

Expected: standard output assertions fail because timestamp columns are absent; agency schema assertions pass.

- [ ] **Step 7: Carry Python stat metadata into standard rows**

Append `Date Created` and `Date Modified` to `REPORT_HEADERS`.

In `iter_scan_files`, replace the three-value yield with:

```python
yield (
    candidate,
    stat.st_size,
    candidate.relative_to(source_dir).as_posix(),
    format_file_timestamp(file_creation_timestamp(stat)),
    format_file_timestamp(getattr(stat, "st_mtime", None)),
)
```

Update both hashing and non-hashing loops in `write_csv_report` to unpack `date_created` and `date_modified`. Extend pending work tuples and change `write_processed_row` to accept both strings. Append them to only the standard row:

```python
date_created,
date_modified,
```

Keep the existing `if agency_template: row = agency_template_row(...)` override unchanged.

- [ ] **Step 8: Update Python golden fixture assertions**

Before the fixture scan, set every kept source file to `FIXED_MODIFIED_EPOCH = 1_714_566_896` using `os.utime`. Replace the direct `self.assertEqual(actual_rows, expected_rows)` with cell-wise comparison that:

- validates `<native-or-unknown>` through `assert_file_timestamp(..., allow_unknown=True)`;
- resolves `<fixed-modified>` to `core.format_file_timestamp(FIXED_MODIFIED_EPOCH)`;
- compares every other cell literally.

- [ ] **Step 9: Mirror the runtime into the Windows deployment source**

Apply the same imports, constants, helper functions, headers, iterator tuple, and row-writing changes to `deploy/windows/scripts/content-list-gen/content_list_core.py`. Verify exact alignment:

```bash
cmp -s python/content_list_core.py deploy/windows/scripts/content-list-gen/content_list_core.py
```

Expected: exit status 0.

- [ ] **Step 10: Run Python tests and parity checks**

Run:

```bash
.venv/bin/python -m unittest discover -s ./python/tests -p 'test_*.py'
./scripts/parity_check.sh
```

Expected: all Python tests and shared Go/Python fixture checks pass.

- [ ] **Step 11: Commit the Python slice**

```bash
git add python/content_list_core.py deploy/windows/scripts/content-list-gen/content_list_core.py python/tests/test_content_scan.py
git commit -m "feat: add file timestamps to Python content lists"
```

---

### Task 3: User Documentation and Full Verification

**Files:**
- Modify: `project-dashboard/user-manual.html:556-572`

**Interfaces:**
- Documents: the exact column names, local-time format, `unknown` fallback, and creation-time caveat shipped by Tasks 1-2.

- [ ] **Step 1: Update the output reference**

After the `Hash Value` row in the content-list column table, add:

```html
<tr><td><code>Date Created</code></td><td>Filesystem creation or birth time in local scan-machine time (<code>YYYY-MM-DD HH:MM:SS ±HH:MM</code>). Shows <code>unknown</code> when the operating system or filesystem does not expose it.</td></tr>
<tr><td><code>Date Modified</code></td><td>Filesystem last-modified time in local scan-machine time (<code>YYYY-MM-DD HH:MM:SS ±HH:MM</code>). Shows <code>unknown</code> when unavailable.</td></tr>
```

Add this caveat below the table:

```html
<p style="margin-top:10px"><strong>Creation-date note:</strong> copying, restoring, downloading, or migrating a file can change its filesystem creation time. It is metadata observed during the scan, not proof of when the document contents were authored.</p>
```

- [ ] **Step 2: Run formatting and mirror checks**

Run:

```bash
gofmt -w file_timestamp.go file_timestamp_darwin.go file_timestamp_windows.go file_timestamp_other.go file_timestamp_test.go core.go scan_test.go
cmp -s python/content_list_core.py deploy/windows/scripts/content-list-gen/content_list_core.py
git diff --check
```

Expected: all commands exit 0 and `git diff --check` prints nothing.

- [ ] **Step 3: Run the complete repository verification suite**

Run with Python 3.12 dependencies available:

```bash
source .venv/bin/activate
./scripts/dev_check.sh
npm --prefix frontend run build
deactivate
```

Expected: Go tests, Go/Python parity, all 13+ Python tests, Python compilation, TypeScript compilation, and Vite build pass.

- [ ] **Step 4: Inspect the final diff and schema boundaries**

Run:

```bash
git diff --stat HEAD~2
git diff HEAD~2 -- core.go python/content_list_core.py deploy/windows/scripts/content-list-gen/content_list_core.py project-dashboard/user-manual.html
git status --short
```

Confirm from the diff that:

- only standard report headers/rows gain two fields;
- both runtime copies use identical labels and fallback text;
- agency, folders-only, email, and clone-difference headers are untouched;
- no generated `frontend/dist` or `.venv` files are staged.

- [ ] **Step 5: Commit documentation**

```bash
git add project-dashboard/user-manual.html
git commit -m "docs: explain file timestamp columns"
```

- [ ] **Step 6: Confirm the branch is ready for review**

Run:

```bash
git status --short --branch
git log -5 --oneline
```

Expected: clean worktree; commits for the approved design, implementation plan, Go implementation, Python implementation, and documentation are visible.
