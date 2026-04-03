# Content List Generator

Written by Bryan Snyder

Content List Generator ships as:

- a Go desktop GUI for macOS and Linux
- a Python desktop GUI for Windows
- built Go Windows `.exe` artifacts in `dist/` for teams that prefer a standalone executable path

Both apps support:

- recursive content-list export to CSV
- optional XLSX generation
- leading-zero preservation in XLSX
- integrated email-file copy with manifest output

Repo-root launchers:

- `./run-go-gui.sh`
- `./run-python-gui.sh`
- `run-python-gui.bat`

Packaged launchers are created in the OS bundle folders:

- macOS: `dist/smoke/macos/run-content-list-generator-gui.sh`
- Linux: `dist/smoke/linux/run-content-list-generator-gui.sh`
- Windows: `dist/smoke/windows-python/run-content-list-generator.bat`

## Windows Paths

Portable Windows GUI bundle:

- repo root launcher: `run-python-gui.bat`
- packaged launcher: `dist/smoke/windows-python/run-content-list-generator.bat`
- keep the whole bundle together if you copy it into a user folder
- bundle contents include:
  - `python/content_list_generator.py`
  - `python/content_list_core.py`
  - `scripts/copy_email_files.py`
  - the `.bat` and `.cmd` launchers
- the Windows bundle `scripts/` folder currently contains `copy_email_files.py`, which remains as a compatibility helper; users do not need to create that folder themselves

Built Go Windows executables:

- `dist/content-list-generator-windows-amd64.exe`
- `dist/content-list-generator-windows-arm64.exe`
- created by `./scripts/build_releases.sh`
- Windows default GUI path is still the Python bundle above

## Start Here

GitHub Pages source:

- [docs/index.md](./docs/index.md)

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
