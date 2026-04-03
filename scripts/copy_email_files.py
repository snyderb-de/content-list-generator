#!/usr/bin/env python3

from __future__ import annotations

import sys
from pathlib import Path


SCRIPT_DIR = Path(__file__).resolve().parent
if (SCRIPT_DIR / "content_list_generator.py").exists():
    PYTHON_DIR = SCRIPT_DIR
else:
    REPO_ROOT = SCRIPT_DIR.parents[1]
    PYTHON_DIR = REPO_ROOT / "python"

if str(PYTHON_DIR) not in sys.path:
    sys.path.insert(0, str(PYTHON_DIR))

from content_list_generator import main  # noqa: E402


if __name__ == "__main__":
    sys.argv.insert(1, "--mode")
    sys.argv.insert(2, "email-copy")
    raise SystemExit(main())
