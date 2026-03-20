#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "$0")/.." && pwd)"
DIST_DIR="$ROOT_DIR/dist"

mkdir -p "$DIST_DIR"

cd "$ROOT_DIR"

go test ./...

GOOS=darwin GOARCH=arm64 go build -o "$DIST_DIR/content-list-generator-darwin-arm64" .
GOOS=windows GOARCH=amd64 go build -o "$DIST_DIR/content-list-generator-windows-amd64.exe" .
GOOS=windows GOARCH=arm64 go build -o "$DIST_DIR/content-list-generator-windows-arm64.exe" .
