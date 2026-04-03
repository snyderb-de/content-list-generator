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

Simplest launch commands from the repo root:

```bash
./run-go-gui.sh
./run-python-gui.sh
```

Fastest packaged path after building the local bundle:

```bash
./scripts/package_macos_local.sh
./dist/smoke/macos/run-content-list-generator-gui.sh
```

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

Simplest launch commands from the repo root:

```bash
./run-go-gui.sh
./run-python-gui.sh
```

Fastest packaged path after building the local bundle:

```bash
./scripts/package_linux_local.sh
./dist/smoke/linux/run-content-list-generator-gui.sh
```

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

Windows has two supported paths.

Portable Python GUI bundle:

```bat
run-python-gui.bat
```

Fastest packaged portable path after building the Windows bundle:

```bat
scripts\package_windows_python_bundle.sh
dist\smoke\windows-python\run-content-list-generator.bat
```

Portable bundle files to keep together when copying into a user folder:

- `python\content_list_generator.py`
- `python\content_list_core.py`
- `scripts\copy_email_files.py`
- `run-content-list-generator.bat`
- `run-content-list-generator.cmd`
- `run-content-list-generator-cli.cmd`
- `run-email-copy.cmd`

The portable bundle `scripts\` folder currently contains only `copy_email_files.py`, which is kept as a compatibility helper. Users do not need to create the `scripts\` folder themselves.

Direct Python command:

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

Built Go Windows executables:

```bat
scripts\build_releases.sh
dist\content-list-generator-windows-amd64.exe
```

Also built:

- `dist\content-list-generator-windows-arm64.exe`

The Windows default GUI path remains the Python bundle. The Go Windows `.exe` files are alternative release artifacts.

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

Packaged launchers end up in:

```bash
./dist/smoke/macos/
```

Linux local bundle:

```bash
./scripts/package_linux_local.sh
```

Packaged launchers end up in:

```bash
./dist/smoke/linux/
```

Windows Python smoke bundle:

```bash
./scripts/package_windows_python_bundle.sh
```

Packaged launchers end up in:

```text
dist\smoke\windows-python\
```

Combined helper:

```bash
./scripts/package_smoke_assets.sh
```
