# Content List Generator

Written by Bryan Snyder

Content List Generator is maintained as two live desktop runtimes that stay in feature parity as closely as practical:

- Go app for macOS and Linux, with optional Windows `.exe` build outputs
- Python app for Windows portable deployment

Both runtimes support:

- recursive content-list export to CSV
- automatic CSV chunking for large scans (default: 300,000 rows per file, named like `report-001.csv`, `report-002.csv`)
- optional XLSX generation
- hash verification modes for migration workflows
- plain-text scan reports
- integrated email-file copy with manifest output

## Runtime And Deploy Paths

Core app/runtime files:

- `main.go`, `core.go`, `gui_fyne.go`, `scan_*.go`
- `python/content_list_generator.py`
- `python/content_list_core.py`

Deploy and distribution files that must stay aligned with the app:

- `deploy/windows/desktop/content-list-generator.bat`
- `deploy/windows/scripts/content-list-gen/content_list_generator.py`
- `deploy/windows/scripts/content-list-gen/content_list_core.py`
- repo-root launchers such as `run-go-gui.sh`, `run-python-gui.sh`, and `content-list-generator.bat`
- packaging helpers in `scripts/`

Generated outputs belong in `build/` and `releases/` and are intentionally not tracked.

## Repo Layout

- `python/` Python runtime code and Python automated tests
- `project-dashboard/` static project dashboard for repo status and docs
- `scripts/` build, parity, packaging, and local-run helpers
- `testing/` tool-oriented fixtures, generators, runners, and ignored local manual-test folders
- `deploy/` copy-ready deployment files that are part of the operational workflow

## Quick Start

```bash
git clone <repo-url>
cd content-list-generator
./scripts/dev_check.sh
```

Local launchers:

- macOS/Linux Go GUI: `./run-go-gui.sh`
- macOS/Linux Python GUI: `./run-python-gui.sh`
- cross-platform helper: `./scripts/run_local.sh [go|go-gui|python|python-cli]`
- Windows desktop launcher: `content-list-generator.bat`

## Platform Notes

macOS and Linux:

- use the Go app
- local binaries are built into `build/`
- local release packages are produced by `./scripts/package_macos_local.sh` or `./scripts/package_linux_local.sh`

Windows portable Python path:

- install Python 3 with Tkinter
- install GUI dependencies with `pip install -r requirements.txt`
- Python defaults to `SHA-1`
- `BLAKE3` is optional on Python and requires the `blake3` package from `requirements.txt`
- copy the deploy bundle from `deploy/windows/` or generate a fresh bundle with `./scripts/package_windows_python_bundle.sh`
- supported launcher lookup paths remain `%USERPROFILE%\\scripts\\` and `%USERPROFILE%\\scripts\\content-list-gen\\`

Windows Go executable path:

- build fresh `.exe` outputs with `./scripts/build_releases.sh`
- generated artifacts land in `releases/windows-go/`

## Testing

Automated checks:

```bash
go test ./...
go test -tags gui ./...
python3 -m unittest discover -s ./python/tests -p 'test_*.py'
python3 -m py_compile python/content_list_core.py python/content_list_generator.py scripts/copy_email_files.py
```

Shared helper scripts:

- `./scripts/dev_check.sh` runs the main smoke suite
- `./scripts/parity_check.sh` runs the cross-language fixture parity checks

Tool-oriented testing layout:

- `testing/content-scan/` contains content-list fixtures, regeneration helpers, and a feature runner
- `testing/email-copy/` contains email-copy fixtures, regeneration helpers, and a feature runner
- `testing/manual-samples/` and `testing/manual-output/` are reserved for ignored machine-local testing data

## Packaging And Releases

Release and local package helpers:

```bash
./scripts/build_releases.sh
./scripts/package_macos_local.sh
./scripts/package_linux_local.sh
./scripts/package_windows_python_bundle.sh
./scripts/package_smoke_assets.sh
./scripts/package_local.sh
```

These scripts generate fresh artifacts in `build/` and `releases/`. The repo no longer treats generated binaries, zips, or tarballs as source files.

## Docs

Canonical docs now live in:

- `README.md` for setup, structure, runtime, and testing
- `TODO.md` for active follow-up work
- `project-dashboard/` for a lightweight static project overview
