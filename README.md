# Content List Generator

Fast terminal app for exporting a recursive file inventory to CSV.

Built with Go and Charm's TUI stack:

- Bubble Tea
- Bubbles
- Lip Gloss
- Glamour

## What it captures

- File Name
- Extension
- Size in Bytes
- Size in Human Readable form
- Path From Root Folder
- SHA-256 hash (optional)

## Current features

- Source folder browser
- Output folder browser
- Output file naming with overwrite confirmation
- Optional SHA-256 hashing
- Optional hidden file exclusion
- Optional common system file exclusion
- Comma-separated extension exclusions
- Optional post-scan XLSX copy generation
- Optional XLSX text-preservation mode for leading zeros
- Optional post-scan email-file copy into a dedicated subfolder with manifest
- Completion summaries by extension count and total size
- Completion summaries for filtered reasons and sample filtered paths
- Parallel hashing when hashes are enabled

## Why CSV

CSV is still a real table, but unlike an in-memory grid it scales cleanly to very large scans. This app streams rows directly to disk, so 500K+ files does not require 500K rows to live in RAM first.

## Build

```bash
go build -o ./bin/content-list-generator .
```

## Run

```bash
./bin/content-list-generator
```

## TUI flow

1. Browse to the source folder
2. Press `space` to choose the current source folder
3. Browse to the output folder
4. Press `space` to choose the current output folder
5. Enter the output `.csv` file name
6. Configure hashing, exclusions, optional XLSX conversion, and optional email-file copy
7. Start the scan
8. If the file already exists, press `y` to overwrite or `n` to go back

## Python backup

There is also a no-dependency Python backup at [python/content_list_generator.py](/Users/baghead/code/content-list-generator/python/content_list_generator.py).
By default it launches a Tkinter desktop GUI with native folder pickers on systems where Tkinter is available.

Run it with:

```bash
python3 ./python/content_list_generator.py
```

For scripted or terminal-only use, force CLI mode:

```bash
python3 ./python/content_list_generator.py --cli
```

It can also run non-interactively:

```bash
python3 ./python/content_list_generator.py --cli \
  --source /path/to/source \
  --output-dir /path/to/output \
  --output-name report.csv \
  --hash \
  --exclude-exts tmp,log \
  --overwrite
```

## Release builds

Use the build script to produce release binaries, including Windows:

```bash
./scripts/build_releases.sh
```

Artifacts are written to `dist/`.

## Notes on large scans

- Hashing is optional because it is the slowest step.
- The scan is recursive.
- Rows are written as they are found.
- CSV is the primary fast scan format.
- If enabled, XLSX is created after the CSV scan completes.
- If enabled, email-related files are copied after the scan into an output subfolder with a CSV manifest.

## Email Copy Utility

There is also a standalone helper at [copy_email_files.py](/Users/baghead/code/content-list-generator/scripts/copy_email_files.py).

Run it with:

```bash
./scripts/copy_email_files.py
```

If you later want a second output mode for truly huge inventories, SQLite is the natural next step.
