# Project Overview

Content List Generator is a desktop tool for two everyday jobs:

1. Make a simple file list from a folder.
2. Copy supported email files into a new folder and save a report.

## Main Features

- Save a content list as CSV
- Optionally save an Excel copy
- Keep leading zeros in Excel when needed
- Copy supported email files into a new folder
- Keep the original folder structure during email copy
- Save a manifest report of copied email files

## Platforms

- macOS and Linux: Go GUI
- Windows: Python GUI with a `.bat` launcher
- Alternate Windows release artifacts: Go `.exe` builds in `releases/windows-go/`

## Windows Portable Layout

- Put `content_list_generator.py`, `content_list_core.py`, and `copy_email_files.py` in `%USERPROFILE%\scripts\`
- Put the launcher `.bat` on the user's Desktop
- The Desktop launcher looks in `%USERPROFILE%\scripts\` first
- The packaged Windows Python release lives in `releases/windows-python/`

## Repo Layout

- `build/` local build outputs
- `releases/` release-ready artifacts by platform
- `testing/` local manual testing workspace
- `docs/` project docs and dashboard content
- `testdata/` tracked automated test fixtures

## Written By

Bryan Snyder

## GitHub

[placeholder link](https://github.com/placeholder/content-list-generator)

## Open Source Note

- This project is being prepared for an open source release.
- TODO: decide the final attribution requirement before publishing.
