# Content List Generator

Written by Bryan Snyder

Content List Generator is maintained as two feature-parity desktop apps:

- Go GUI for macOS and Linux
- Python GUI for Windows
- alternate Go Windows `.exe` artifacts for teams that want a standalone executable path

Both app paths support:

- recursive content-list export to CSV
- optional XLSX generation
- leading-zero preservation in XLSX
- integrated email-file copy with manifest output

## Repo Layout

- `docs/` long-form project docs and GitHub Pages content
- `python/` Python app source and Python-side tests
- `scripts/` build, release, parity, and local run helpers
- `build/` local build outputs
- `releases/` release-ready artifacts and packaged outputs
- `testing/` local manual testing workspace
- `testdata/` tracked automated test fixtures

## Clone And Run

```bash
git clone <repo-url>
cd content-list-generator
./scripts/dev_check.sh
```

Repo-root launchers:

- macOS/Linux Go GUI: `./run-go-gui.sh`
- macOS/Linux Python GUI: `./run-python-gui.sh`
- Windows Python GUI launcher: `content-list-generator.bat`
- legacy Windows launcher: `run-python-gui.bat`

## Install By OS

macOS and Linux:

- install Go
- run `./run-go-gui.sh` from the repo root for the Go GUI
- local binaries are written to `build/`

Windows, portable Python GUI path:

- install Python 3 with Tkinter
- install the Python dependency with `pip install -r requirements.txt`
- `releases/windows-python/` contains the Windows Python deployment files
- copy these files to `%USERPROFILE%\scripts\`:
  - `content_list_generator.py`
  - `content_list_core.py`
- place `content-list-generator.bat` on the user's Desktop, or use `releases/windows-python/content-list-generator.bat`
- launcher search order supports both `%USERPROFILE%\scripts\` and `%USERPROFILE%\scripts\content-list-gen\`
- legacy launchers still work: `run-python-gui.bat`, `releases/windows-python/launch-content-list-generator-gui.bat`, and `releases/windows-python/run-content-list-generator.bat`

Windows, Go executable path:

- run `./scripts/build_releases.sh`
- use the built artifacts in `releases/windows-go/`
- current Windows Go artifacts:
  - `releases/windows-go/content-list-generator-windows-amd64.exe`
  - `releases/windows-go/content-list-generator-windows-arm64.exe`

## Build And Add Feature

Recommended local workflow:

```bash
git clone <repo-url>
cd content-list-generator
./scripts/dev_check.sh
./scripts/run_local.sh go-gui
./scripts/run_local.sh python
```

Useful commands:

```bash
go test ./...
go test -tags gui ./...
python3 -m unittest discover -s ./python -p 'test_*.py'
python3 -m py_compile python/content_list_core.py python/content_list_generator.py scripts/copy_email_files.py
```

Release helpers:

```bash
./scripts/build_releases.sh
./scripts/package_macos_local.sh
./scripts/package_linux_local.sh
./scripts/package_windows_python_bundle.sh
./scripts/package_smoke_assets.sh
```

## Release Outputs

- macOS release artifacts live in `releases/macos/`
- Linux release artifacts live in `releases/linux/`
- Windows Python release artifacts live in `releases/windows-python/`
- Windows Go release artifacts live in `releases/windows-go/`

## Project Docs

- install and run: [INSTALL.md](./INSTALL.md)
- smoke test plan: [SMOKE_TEST_PLAN.md](./SMOKE_TEST_PLAN.md)
- project TODO list: [TODO.md](./TODO.md)
- docs index: [docs/index.md](./docs/index.md)
