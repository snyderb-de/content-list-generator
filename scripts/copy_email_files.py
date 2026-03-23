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
    from tkinter import filedialog, messagebox, ttk
except Exception:  # pragma: no cover
    tk = None
    filedialog = None
    messagebox = None
    ttk = None


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
        help="Use text prompts instead of the small GUI",
    )
    return parser.parse_args()


def prompt(text: str, default: str = "") -> str:
    suffix = f" [{default}]" if default else ""
    value = input(f"{text}{suffix}: ").strip()
    return value or default


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
                "Relative Path": relative.as_posix(),
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


def run_copy(source: Path, dest: Path) -> tuple[int, Path]:
    if not source.is_dir():
        raise ValueError(f"Source folder does not exist: {source}")

    dest.mkdir(parents=True, exist_ok=True)
    matches = collect_matches(source)
    if not matches:
        return 0, dest / "no-manifest-created.csv"

    copied_rows = copy_matches(source, dest, matches)
    manifest_path = write_manifest(dest, copied_rows)
    return len(copied_rows), manifest_path


class EmailCopyApp:
    def __init__(self, source: str = "", dest: str = "") -> None:
        self.root = tk.Tk()
        self.root.title("Copy Email Files")
        self.root.geometry("760x360")
        self.root.minsize(700, 320)
        self.root.configure(bg="#f3f5f8")

        self.source_var = tk.StringVar(value=source or str(Path.cwd()))
        self.dest_var = tk.StringVar(value=dest or "")
        self.status_var = tk.StringVar(value="Choose the source and destination folders.")

        self.configure_style()
        self.build_ui()

    def configure_style(self) -> None:
        style = ttk.Style()
        if "clam" in style.theme_names():
            style.theme_use("clam")
        style.configure("App.TFrame", background="#f3f5f8")
        style.configure("Card.TFrame", background="#ffffff")
        style.configure("Title.TLabel", background="#f3f5f8", foreground="#12324a", font=("Segoe UI", 22, "bold"))
        style.configure("Body.TLabel", background="#ffffff", foreground="#243746", font=("Segoe UI", 11))
        style.configure("Hint.TLabel", background="#f3f5f8", foreground="#5b6b79", font=("Segoe UI", 10))

    def build_ui(self) -> None:
        outer = ttk.Frame(self.root, style="App.TFrame", padding=24)
        outer.pack(fill="both", expand=True)

        ttk.Label(outer, text="Copy Email Files", style="Title.TLabel").pack(anchor="w")
        ttk.Label(
            outer,
            text="This preserves the original folder structure from the chosen source root.",
            style="Hint.TLabel",
        ).pack(anchor="w", pady=(6, 18))

        card = ttk.Frame(outer, style="Card.TFrame", padding=20)
        card.pack(fill="both", expand=True)
        card.columnconfigure(1, weight=1)

        ttk.Label(card, text="Source folder", style="Body.TLabel").grid(row=0, column=0, sticky="w", pady=8, padx=(0, 12))
        ttk.Button(card, text="Choose Source", command=self.choose_source).grid(row=0, column=1, sticky="w")
        ttk.Label(card, textvariable=self.source_var, style="Body.TLabel", wraplength=500, justify="left").grid(
            row=1, column=1, sticky="w", pady=(0, 12)
        )

        ttk.Label(card, text="Destination folder", style="Body.TLabel").grid(row=2, column=0, sticky="w", pady=8, padx=(0, 12))
        ttk.Button(card, text="Choose Destination", command=self.choose_dest).grid(row=2, column=1, sticky="w")
        ttk.Label(card, textvariable=self.dest_var, style="Body.TLabel", wraplength=500, justify="left").grid(
            row=3, column=1, sticky="w", pady=(0, 12)
        )

        ttk.Label(
            card,
            text="Included extensions: " + ", ".join(sorted(EMAIL_EXTENSIONS)),
            style="Body.TLabel",
            wraplength=620,
            justify="left",
        ).grid(row=4, column=0, columnspan=2, sticky="w", pady=(8, 14))

        ttk.Button(card, text="Start Copy", command=self.start_copy).grid(row=5, column=0, columnspan=2, sticky="w")
        ttk.Label(card, textvariable=self.status_var, style="Body.TLabel", wraplength=620, justify="left").grid(
            row=6, column=0, columnspan=2, sticky="w", pady=(14, 0)
        )

    def choose_source(self) -> None:
        selected = filedialog.askdirectory(title="Choose Source Folder", initialdir=self.source_var.get() or str(Path.cwd()), mustexist=True)
        if selected:
            self.source_var.set(selected)
            if not self.dest_var.get():
                self.status_var.set("Source selected. Now choose the destination folder.")

    def choose_dest(self) -> None:
        initial = self.dest_var.get() or self.source_var.get() or str(Path.cwd())
        selected = filedialog.askdirectory(title="Choose Destination Folder", initialdir=initial, mustexist=False)
        if selected:
            self.dest_var.set(selected)
            self.status_var.set("Destination selected. Click Start Copy when you're ready.")

    def start_copy(self) -> None:
        source_raw = self.source_var.get().strip()
        dest_raw = self.dest_var.get().strip()
        if not source_raw:
            messagebox.showerror("Missing source", "Choose a source folder first.")
            return
        if not dest_raw:
            messagebox.showerror("Missing destination", "Choose a destination folder first.")
            return

        source = Path(source_raw).expanduser().resolve()
        dest = Path(dest_raw).expanduser().resolve()

        try:
            copied, manifest = run_copy(source, dest)
        except Exception as exc:
            messagebox.showerror("Copy failed", str(exc))
            return

        if copied == 0:
            self.status_var.set("No matching email files were found.")
            messagebox.showinfo("Done", "No matching email files were found.")
            return

        self.status_var.set(f"Copied {copied} files.\nManifest: {manifest}")
        messagebox.showinfo(
            "Done",
            f"Copied {copied} files.\n\nDestination: {dest}\nManifest: {manifest}",
        )

    def run(self) -> int:
        self.root.mainloop()
        return 0


def run_cli(args: argparse.Namespace) -> int:
    source_raw = args.source or prompt("Source folder", str(Path.cwd()))
    dest_raw = args.dest or prompt("Destination folder")

    if not source_raw:
        print("Source folder is required.", file=sys.stderr)
        return 1
    if not dest_raw:
        print("Destination folder is required.", file=sys.stderr)
        return 1

    source = Path(source_raw).expanduser().resolve()
    dest = Path(dest_raw).expanduser().resolve()

    print("\nScanning...")
    copied, manifest = run_copy(source, dest)

    if copied == 0:
        print("No matching email files were found.")
        return 0

    print("\nDone")
    print(f"Source: {source}")
    print(f"Destination: {dest}")
    print(f"Copied: {copied}")
    print(f"Manifest: {manifest}")
    print("Extensions included:")
    print("  " + ", ".join(sorted(EMAIL_EXTENSIONS)))
    print("")
    print("Mode: preserve relative folders from the chosen source root")
    return 0


def main() -> int:
    args = parse_args()
    if not args.cli and tk is not None:
        return EmailCopyApp(args.source or "", args.dest or "").run()
    return run_cli(args)


if __name__ == "__main__":
    raise SystemExit(main())
