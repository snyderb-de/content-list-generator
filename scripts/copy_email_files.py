#!/usr/bin/env python3

from __future__ import annotations

import argparse
import csv
import shutil
import sys
import time
from pathlib import Path

try:
    import tkinter as tk
    from tkinter import filedialog
except Exception:  # pragma: no cover
    tk = None
    filedialog = None


EMAIL_EXTENSIONS = {
    ".dbx",
    ".eml",
    ".emlx",
    ".emlxpart",
    ".mbox",
    ".mbx",
    ".msg",
    ".olk14msgsource",
    ".ost",
    ".pst",
    ".rge",
    ".tbb",
    ".wdseml",
}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Copy email-related files from a source tree into a destination folder."
    )
    parser.add_argument("--source", help="Folder to scan")
    parser.add_argument("--dest", help="Folder to copy matching files into")
    parser.add_argument(
        "--cli",
        action="store_true",
        help="Use text prompts instead of native folder pickers",
    )
    return parser.parse_args()


def prompt(text: str, default: str = "") -> str:
    suffix = f" [{default}]" if default else ""
    value = input(f"{text}{suffix}: ").strip()
    return value or default


def choose_folder(title: str, initial_dir: Path) -> str:
    if tk is None or filedialog is None:
        return ""

    root = tk.Tk()
    root.withdraw()
    root.attributes("-topmost", True)
    try:
        return filedialog.askdirectory(title=title, initialdir=str(initial_dir), mustexist=True)
    finally:
        root.destroy()


def collect_matches(source: Path) -> list[Path]:
    matches: list[Path] = []
    for path in source.rglob("*"):
        if not path.is_file():
            continue
        if path.suffix.lower() in EMAIL_EXTENSIONS:
            matches.append(path)
    matches.sort()
    return matches


def copy_matches(source: Path, dest: Path, matches: list[Path]) -> list[dict[str, str]]:
    copied_rows: list[dict[str, str]] = []

    for path in matches:
        relative = path.relative_to(source)
        target = dest / relative

        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(path, target)

        copied_rows.append(
            {
                "Source Path": str(path),
                "Destination Path": str(target),
                "Relative Path": str(path.relative_to(source)),
                "File Name": path.name,
                "Extension": path.suffix.lower(),
                "Size in Bytes": str(path.stat().st_size),
            }
        )

    return copied_rows


def write_manifest(dest: Path, rows: list[dict[str, str]]) -> Path:
    timestamp = time.strftime("%Y-%m-%dT%H-%M-%S")
    manifest_path = dest / f"email-copy-manifest-{timestamp}.csv"
    with manifest_path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(
            handle,
            fieldnames=[
                "Source Path",
                "Destination Path",
                "Relative Path",
                "File Name",
                "Extension",
                "Size in Bytes",
            ],
        )
        writer.writeheader()
        writer.writerows(rows)
    return manifest_path


def pick_paths(args: argparse.Namespace) -> tuple[str, str]:
    if args.source and args.dest:
        return args.source, args.dest

    if not args.cli and tk is not None:
        source_choice = args.source or choose_folder("Choose source folder", Path.cwd())
        if not source_choice:
            return "", ""
        dest_choice = args.dest or choose_folder("Choose destination folder", Path(source_choice))
        return source_choice, dest_choice

    source_choice = args.source or prompt("Source folder", str(Path.cwd()))
    dest_choice = args.dest or prompt("Destination folder")
    return source_choice, dest_choice


def main() -> int:
    args = parse_args()
    source_raw, dest_raw = pick_paths(args)

    if not source_raw:
        print("Source folder is required.", file=sys.stderr)
        return 1
    if not dest_raw:
        print("Destination folder is required.", file=sys.stderr)
        return 1

    source = Path(source_raw).expanduser().resolve()
    dest = Path(dest_raw).expanduser().resolve()

    if not source.is_dir():
        print(f"Source folder does not exist: {source}", file=sys.stderr)
        return 1

    dest.mkdir(parents=True, exist_ok=True)

    print("\nScanning...")
    matches = collect_matches(source)

    print(f"Found {len(matches)} matching files.")
    if not matches:
        print("Nothing to copy.")
        return 0

    copied_rows = copy_matches(source, dest, matches)
    manifest_path = write_manifest(dest, copied_rows)

    print("\nDone")
    print(f"Source: {source}")
    print(f"Destination: {dest}")
    print(f"Copied: {len(copied_rows)}")
    print(f"Manifest: {manifest_path}")
    print("Extensions included:")
    print("  " + ", ".join(sorted(EMAIL_EXTENSIONS)))
    print("")
    print("Mode: preserve relative folders from the chosen source root")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
