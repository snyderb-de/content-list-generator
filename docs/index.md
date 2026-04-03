# Content List Generator

Written by Bryan Snyder

GitHub:
[placeholder link](https://github.com/placeholder/content-list-generator)

Content List Generator helps people create a simple file list from a folder and copy supported email files into a new location with a saved report.

## Project Status

- Desktop app for macOS and Linux: Go GUI
- Desktop app for Windows: Python GUI with a `.bat` launcher
- Alternate Windows release artifacts: Go `.exe` files in `dist/`
- Open source release: planned
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

## Notes

- The content-list workflow saves a CSV file and can also save an Excel copy.
- The email-copy workflow looks for supported email file types, copies matching files, keeps the original folder layout, and saves a report.
- The Windows portable bundle keeps the Python app under `python/` and a compatibility helper under `scripts/copy_email_files.py`.
