# Install And Run

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

## Quickest Way To Launch

From the repo root:

```bash
./run-go-gui.sh
./run-python-gui.sh
```

## Packaged Bundle Paths

macOS:

```bash
./scripts/package_macos_local.sh
./dist/smoke/macos/run-content-list-generator-gui.sh
```

Linux:

```bash
./scripts/package_linux_local.sh
./dist/smoke/linux/run-content-list-generator-gui.sh
```

Windows:

```bat
scripts\package_windows_python_bundle.sh
dist\smoke\windows-python\run-content-list-generator.cmd
```

## Verify Before Running

```bash
./scripts/dev_check.sh
./scripts/parity_check.sh
```
