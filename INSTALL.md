# Install And Run

This project ships with:

- a Go desktop GUI for macOS and Linux
- a Python desktop GUI for Windows

There are also fallback command-line paths, but the GUI is the default product on each OS.

## What You Need

macOS:

- Go installed

Linux:

- Go installed
- a desktop session if you want the Go GUI

Windows:

- Python 3 installed
- Tkinter available with Python

## Get The Repo

```bash
git clone <repo-url>
cd content-list-generator
```

## macOS

Build the Go GUI:

```bash
go build -tags gui -o ./bin/content-list-generator-gui .
```

Run it:

```bash
./bin/content-list-generator-gui --gui
```

Quick helper:

```bash
./scripts/run_local.sh go-gui
```

Fallback TUI:

```bash
./scripts/run_local.sh go
```

## Linux

Build the Go GUI:

```bash
go build -tags gui -o ./bin/content-list-generator-gui .
```

Run it:

```bash
./bin/content-list-generator-gui --gui
```

Quick helper:

```bash
./scripts/run_local.sh go-gui
```

Fallback TUI:

```bash
./scripts/run_local.sh go
```

## Windows

Run the Python GUI:

```bash
python .\python\content_list_generator.py
```

Compatibility launcher for email copy:

```bash
python .\scripts\copy_email_files.py
```

CLI fallback:

```bash
python .\python\content_list_generator.py --cli
```

## Verify Before Running

Run the full local checks:

```bash
./scripts/dev_check.sh
```

Run just the cross-language parity checks:

```bash
./scripts/parity_check.sh
```

## Optional Smoke Bundles

macOS local bundle:

```bash
./scripts/package_macos_local.sh
```

Linux local bundle:

```bash
./scripts/package_linux_local.sh
```

Windows Python smoke bundle:

```bash
./scripts/package_windows_python_bundle.sh
```

Combined helper:

```bash
./scripts/package_smoke_assets.sh
```
