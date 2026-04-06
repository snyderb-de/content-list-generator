# Install And Run

## Requirements

macOS:

- Go installed

Linux:

- Go installed
- a desktop session for the Go GUI

Windows, Python GUI path:

- Python 3 installed
- Tkinter available with Python
- install dependencies with `pip install -r requirements.txt`

## Clone The Repo

```bash
git clone <repo-url>
cd content-list-generator
```

## macOS

Run the Go GUI from the repo root:

```bash
./run-go-gui.sh
```

Local Go build output:

```text
build/content-list-generator-gui
```

Build the macOS release package:

```bash
./scripts/package_macos_local.sh
```

Release files end up in:

```text
releases/macos/
```

## Linux

Run the Go GUI from the repo root:

```bash
./run-go-gui.sh
```

Local Go build output:

```text
build/content-list-generator-gui
```

Build the Linux release package on a Linux machine:

```bash
./scripts/package_linux_local.sh
```

Release files end up in:

```text
releases/linux/
```

## Windows

Windows has two supported install paths.

### Path A: Portable Python GUI

Install the Python dependency first:

```bash
pip install -r requirements.txt
```

Put these files in:

```text
C:\Users\[USER]\scripts\content-list-gen\
```

Files to copy:

- `content_list_generator.py`
- `content_list_core.py`
- `copy_email_files.py`

Put one of these launchers on the user's Desktop:

- `content-list-generator.bat`
- `releases/windows-python/content-list-generator.bat`

Legacy launchers still supported:

- `run-python-gui.bat`
- `releases/windows-python/launch-content-list-generator-gui.bat`
- `releases/windows-python/run-content-list-generator.bat`

Build the portable Windows Python package:

```bash
./scripts/package_windows_python_bundle.sh
```

Release files end up in:

```text
releases/windows-python/
```

### Path B: Go Windows Executable

Build the Windows Go artifacts:

```bash
./scripts/build_releases.sh
```

Use the executables in:

```text
releases/windows-go/
```

Current files:

- `releases/windows-go/content-list-generator-windows-amd64.exe`
- `releases/windows-go/content-list-generator-windows-arm64.exe`

## Development Checks

Run the full local checks:

```bash
./scripts/dev_check.sh
```

Run the cross-language parity checks:

```bash
./scripts/parity_check.sh
```
