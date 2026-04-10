from __future__ import annotations

import json
import shutil
from pathlib import Path


FIXTURE_DIR = Path(__file__).resolve().parent / "fixtures"
SOURCE_DIR = FIXTURE_DIR / "source"
EXPECTED_JSON = FIXTURE_DIR / "expected-email-manifest.json"

SOURCE_FILES = {
    ".hidden/secret.txt": b"secret\n",
    "Thumbs.db": b"thumbs\n",
    "keep.txt": b"keep\n",
    "mail/archive.pst": b"archive-body\n",
    "mail/inbox.eml": b"mail-body\n",
    "nested/0007.txt": b"0007\n",
    "nested/data.bin": b"binary-data\n",
    "skip.log": b"skip\n",
}

EXPECTED_ROWS = [
    {
        "Relative Path": "mail/archive.pst",
        "File Name": "archive.pst",
        "Extension": ".pst",
        "Size in Bytes": "13",
    },
    {
        "Relative Path": "mail/inbox.eml",
        "File Name": "inbox.eml",
        "Extension": ".eml",
        "Size in Bytes": "10",
    },
]


def write_source_tree() -> None:
    if SOURCE_DIR.exists():
        shutil.rmtree(SOURCE_DIR)
    SOURCE_DIR.mkdir(parents=True)
    for relative_path, content in SOURCE_FILES.items():
        target = SOURCE_DIR / relative_path
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(content)


def write_expected_json() -> None:
    EXPECTED_JSON.write_text(
        json.dumps({"copied": 2, "rows": EXPECTED_ROWS}, indent=2) + "\n",
        encoding="utf-8",
    )


if __name__ == "__main__":
    write_source_tree()
    write_expected_json()
