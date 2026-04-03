# Content List Generator

Written by Bryan Snyder

GitHub:
[placeholder link](https://github.com/placeholder/content-list-generator)

Content List Generator helps people create a simple file list from a folder and copy supported email files into a new location with a saved report.

## Project Status

- Desktop app for macOS and Linux: Go GUI
- Desktop app for Windows: Python GUI with a `.bat` launcher
- Alternate Windows release artifacts: Go `.exe` files in `releases/windows-go/`
- Open source release: planned
- License decision: TODO decide before public release
- Attribution requirement: TODO decide before public release

## Start Here

- [Project overview](./readme.md)
- [Install and run](./install.md)
- [Developer build guide](./dev-build.md)
- [Issues and TODOs](./issues-and-todos.md)
- [Future release ideas](./release-ideas.md)

## Quick Launch

From the repo root:

```bash
./run-go-gui.sh
./run-python-gui.sh
```

Windows Desktop launcher:

```bat
run-python-gui.bat
```

## Notes

- The content-list workflow saves a CSV file and can also save an Excel copy.
- The email-copy workflow looks for supported email file types, copies matching files, keeps the original folder layout, and saves a report.
- The Windows Desktop launcher expects the Python files in `%USERPROFILE%\scripts\`.
- The packaged Windows bundle keeps those Python files together under `releases/windows-python/scripts/` so they can be copied into `%USERPROFILE%\scripts\`.
- Release outputs now live under `releases/`, and local build outputs live under `build/`.
- The main repo TODO list lives in `TODO.md` at the repo root.
