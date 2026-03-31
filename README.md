# Content List Generator

Content List Generator now ships as two full apps with matching core behavior:

- Go TUI app for the cross-platform terminal workflow
- Python Tkinter app as the Windows-native full-app path

Both apps include two first-class workflows:

- Generate a recursive content list to CSV, with optional XLSX export
- Copy email-related files into a chosen destination with a manifest report

## Architecture

- `main.go` is the main Go terminal app.
- `python/content_list_generator.py` is the Windows-native Python full app and CLI entry point.
- `scripts/copy_email_files.py` is now a thin compatibility wrapper that launches the Python app's integrated email-copy mode instead of owning separate logic.

## Content List Workflow

Both full apps support:

- Source folder selection
- Output folder selection
- Output CSV naming with overwrite confirmation
- Optional SHA-256 hashing
- Optional hidden file exclusion
- Optional common system file exclusion
- Comma-separated extension exclusions
- Optional XLSX generation after the CSV scan
- Optional XLSX text-preservation mode for leading zeros
- Completion summaries by extension count and total size

The CSV columns are:

- File Name
- Extension
- Size in Bytes
- Size in Human Readable
- Path From Root Folder
- SHA256 Hash

## Email Copy Workflow

Email copy is now a sub-feature inside both full apps rather than the primary UX of a standalone script.

The dedicated email-copy flow in both apps:

- asks for a source folder
- asks where to copy the email files
- preserves the original relative folder structure from the chosen source root
- writes a manifest report in the destination folder

The manifest columns are:

- Source Path
- Destination Path
- Relative Path
- File Name
- Extension
- Size in Bytes

Supported extensions:

- `.dbx`
- `.eml`
- `.emlx`
- `.emlxpart`
- `.mbox`
- `.mbx`
- `.msg`
- `.olk14msgsource`
- `.ost`
- `.pst`
- `.rge`
- `.tbb`
- `.wdseml`

## Why CSV First

CSV is still the safest default for large scans because rows are streamed directly to disk instead of being held in memory as a giant in-app table.

## Build

```bash
go build -o ./bin/content-list-generator .
```

## Run The Go App

```bash
./bin/content-list-generator
```

The Go app opens to a main menu where you choose either:

- `Generate Content List`
- `Copy Email Files`

## Run The Python App

```bash
python3 ./python/content_list_generator.py
```

By default the Python app launches the desktop GUI when Tkinter is available and no explicit CLI arguments are provided.

CLI scan mode:

```bash
python3 ./python/content_list_generator.py --cli \
  --source /path/to/source \
  --output-dir /path/to/output \
  --output-name report.csv \
  --hash \
  --xlsx \
  --preserve-zeros \
  --exclude-exts tmp,log \
  --overwrite
```

CLI email-copy mode:

```bash
python3 ./python/content_list_generator.py --cli \
  --mode email-copy \
  --source /path/to/source \
  --dest /path/to/destination
```

Compatibility wrapper:

```bash
./scripts/copy_email_files.py
```

## Testing

Go:

```bash
go test ./...
```

Python:

```bash
python3 -m unittest discover -s ./python -p 'test_*.py'
python3 -m py_compile ./python/content_list_generator.py ./scripts/copy_email_files.py
```

The automated coverage now includes:

- CSV scan output
- XLSX generation
- leading-zero preservation in XLSX
- integrated email-copy output
- manifest/report generation
- Python non-GUI core behavior

## Release Builds

Use the release script to rebuild the distributable artifacts:

```bash
./scripts/build_releases.sh
```

This writes release binaries to `dist/` and the local Go binary to `bin/content-list-generator`.
