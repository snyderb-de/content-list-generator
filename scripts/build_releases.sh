#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "$0")/.." && pwd)"
RELEASES_DIR="$ROOT_DIR/releases"
MACOS_DIR="$RELEASES_DIR/macos"
LINUX_DIR="$RELEASES_DIR/linux"
WINDOWS_GO_DIR="$RELEASES_DIR/windows-go"
WINDOWS_PY_DIR="$RELEASES_DIR/windows-python"

mkdir -p "$MACOS_DIR" "$LINUX_DIR" "$WINDOWS_GO_DIR" "$WINDOWS_PY_DIR"

cd "$ROOT_DIR"

go test ./...

GOOS=darwin GOARCH=arm64 go build -o "$MACOS_DIR/content-list-generator-darwin-arm64" .
GOOS=windows GOARCH=amd64 go build -o "$WINDOWS_GO_DIR/content-list-generator-windows-amd64.exe" .
GOOS=windows GOARCH=arm64 go build -o "$WINDOWS_GO_DIR/content-list-generator-windows-arm64.exe" .
