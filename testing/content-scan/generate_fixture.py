from __future__ import annotations

import csv
import hashlib
import shutil
from pathlib import Path


FIXTURE_DIR = Path(__file__).resolve().parent / "fixtures"
SOURCE_DIR = FIXTURE_DIR / "source"
EXPECTED_CSV = FIXTURE_DIR / "expected-scan-hash.csv"

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

KEPT_FILES = [
    "keep.txt",
    "mail/archive.pst",
    "mail/inbox.eml",
    "nested/0007.txt",
    "nested/data.bin",
]


def write_source_tree() -> None:
    if SOURCE_DIR.exists():
        shutil.rmtree(SOURCE_DIR)
    SOURCE_DIR.mkdir(parents=True)
    for relative_path, content in SOURCE_FILES.items():
        target = SOURCE_DIR / relative_path
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(content)


def human_size(size: int) -> str:
    return f"{size} B"


def write_expected_csv() -> None:
    with EXPECTED_CSV.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.writer(handle)
        writer.writerow(
            [
                "File Name",
                "Extension",
                "Size in Bytes",
                "Size in Human Readable",
                "Path From Root Folder",
                "Hash Algorithm",
                "Hash Value",
            ]
        )
        for relative_path in KEPT_FILES:
            full_path = SOURCE_DIR / relative_path
            data = full_path.read_bytes()
            writer.writerow(
                [
                    full_path.name,
                    full_path.suffix.lstrip("."),
                    len(data),
                    human_size(len(data)),
                    relative_path,
                    "SHA-256",
                    hashlib.sha256(data).hexdigest(),
                ]
            )


if __name__ == "__main__":
    write_source_tree()
    write_expected_csv()
