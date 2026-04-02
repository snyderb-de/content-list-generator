# Content List Generator

Content List Generator ships as:

- a Go desktop GUI for macOS and Linux
- a Python desktop GUI for Windows

Both apps support:

- recursive content-list export to CSV
- optional XLSX generation
- leading-zero preservation in XLSX
- integrated email-file copy with manifest output

Packaged launchers are created in the OS bundle folders:

- macOS: `dist/smoke/macos/run-content-list-generator-gui.sh`
- Linux: `dist/smoke/linux/run-content-list-generator-gui.sh`
- Windows: `dist/smoke/windows-python/run-content-list-generator.cmd`

## Start Here

Install and run instructions:

- [INSTALL.md](./INSTALL.md)

Manual smoke-test guide:

- [SMOKE_TEST_PLAN.md](./SMOKE_TEST_PLAN.md)

## Fast Commands

Full local checks:

```bash
./scripts/dev_check.sh
```

Cross-language parity checks:

```bash
./scripts/parity_check.sh
```

Local run helpers:

```bash
./scripts/run_local.sh go
./scripts/run_local.sh go-gui
./scripts/run_local.sh python
./scripts/run_local.sh python-cli -- --help
```

Smoke-package helpers:

```bash
./scripts/package_macos_local.sh
./scripts/package_linux_local.sh
./scripts/package_windows_python_bundle.sh
./scripts/package_smoke_assets.sh
```

## Project Notes

- macOS/Linux default shipped app: Go GUI
- Windows default shipped app: Python GUI
- Go TUI remains available as a fallback path
- shared parity fixtures live under `testdata/parity/`
