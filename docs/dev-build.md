# Developer Build Guide

## Repo Root Launchers

```bash
./run-go-gui.sh
./run-python-gui.sh
```

Windows repo-root launcher:

```bat
run-python-gui.bat
```

## Local Checks

```bash
./scripts/dev_check.sh
```

## Local Build Outputs

- Go local binaries are written to `build/`
- helper-built release outputs are written to `releases/`

## Go Tests

```bash
go test ./...
go test -tags gui ./...
```

## Python Tests

```bash
python3 -m unittest discover -s ./python -p 'test_*.py'
python3 -m py_compile python/content_list_core.py python/content_list_generator.py python/test_content_list_generator.py
```

## Packaging Helpers

```bash
./scripts/build_releases.sh
./scripts/package_macos_local.sh
./scripts/package_linux_local.sh
./scripts/package_windows_python_bundle.sh
./scripts/package_smoke_assets.sh
```

## Shared Parity Fixtures

Shared parity test data lives in `testdata/parity/`.
