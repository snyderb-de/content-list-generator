#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "$0")" && pwd)"
cd "$ROOT_DIR"

export PATH="$PATH:$(go env GOPATH)/bin"
exec wails dev -appargs "--gui"
