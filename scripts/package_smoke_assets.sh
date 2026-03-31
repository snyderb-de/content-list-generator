#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "$0")/.." && pwd)"

cd "$ROOT_DIR"

case "$(uname -s)" in
  Darwin)
    ./scripts/package_macos_local.sh
    ;;
  Linux)
    ./scripts/package_linux_local.sh
    ;;
  *)
    echo "Skipping local Go GUI smoke bundle on this OS."
    ;;
esac

./scripts/package_windows_python_bundle.sh

echo "Smoke packaging complete."
