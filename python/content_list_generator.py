#!/usr/bin/env python3

from __future__ import annotations

import argparse
import csv
import hashlib
import os
import queue
import sys
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

try:
    import tkinter as tk
    from tkinter import filedialog, messagebox, ttk
except Exception:  # pragma: no cover
    tk = None
    filedialog = None
    messagebox = None
    ttk = None


SYSTEM_FILES = {".ds_store", "thumbs.db", "desktop.ini", "ehthumbs.db"}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Recursive content list generator")
    parser.add_argument("--source")
    parser.add_argument("--output-dir")
    parser.add_argument("--output-name")
    parser.add_argument("--hash", action="store_true", dest="hashing")
    parser.add_argument("--include-hidden", action="store_true")
    parser.add_argument("--include-system", action="store_true")
    parser.add_argument("--exclude-exts", default="")
    parser.add_argument("--overwrite", action="store_true")
    parser.add_argument("--cli", action="store_true", help="Force CLI mode instead of Tkinter GUI")
    return parser.parse_args()


def prompt(text: str, default: str = "") -> str:
    if not sys.stdin.isatty():
        return default
    suffix = f" [{default}]" if default else ""
    value = input(f"{text}{suffix}: ").strip()
    return value or default


def prompt_yes_no(text: str, default: bool = False) -> bool:
    if not sys.stdin.isatty():
        return default
    hint = "Y/n" if default else "y/N"
    value = input(f"{text} [{hint}]: ").strip().lower()
    if not value:
        return default
    return value in {"y", "yes"}


def normalize_exts(raw: str) -> set[str]:
    result: set[str] = set()
    for part in raw.split(","):
        clean = part.strip().lower().lstrip(".")
        if clean:
            result.add(clean)
    return result


def default_output_name(source_dir: Path) -> str:
    stamp = time.strftime("%Y-%m-%dT%H-%M-%S")
    base = source_dir.name or "content-list"
    return f"{base}-content-list-{stamp}.csv"


def is_hidden_path(path: Path, source_root: Path) -> bool:
    relative = path.relative_to(source_root)
    return any(part.startswith(".") for part in relative.parts)


def should_skip(path: Path, source_root: Path, include_hidden: bool, include_system: bool, excluded_exts: set[str]) -> bool:
    if not include_hidden and is_hidden_path(path, source_root):
        return True
    if not include_system and path.name.lower() in SYSTEM_FILES:
        return True
    if path.suffix.lower().lstrip(".") in excluded_exts:
        return True
    return False


def hash_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def human_bytes(size: int) -> str:
    units = ["B", "KB", "MB", "GB", "TB", "PB"]
    value = float(size)
    index = 0
    while value >= 1024 and index < len(units) - 1:
        value /= 1024
        index += 1
    if index == 0:
        return f"{size} {units[index]}"
    if value >= 10:
        return f"{value:.1f} {units[index]}"
    return f"{value:.2f} {units[index]}"


def collect_files(source_dir: Path, include_hidden: bool, include_system: bool, excluded_exts: set[str]) -> tuple[list[Path], int]:
    kept: list[Path] = []
    filtered = 0
    for root, dirs, files in os.walk(source_dir):
        root_path = Path(root)
        if not include_hidden:
            visible_dirs = []
            for directory in dirs:
                candidate = root_path / directory
                if is_hidden_path(candidate, source_dir):
                    filtered += 1
                    continue
                visible_dirs.append(directory)
            dirs[:] = visible_dirs

        for file_name in files:
            candidate = root_path / file_name
            if should_skip(candidate, source_dir, include_hidden, include_system, excluded_exts):
                filtered += 1
                continue
            kept.append(candidate)
    return kept, filtered


def write_report(
    source_dir: Path,
    output_path: Path,
    files: list[Path],
    hashing: bool,
    progress_callback=None,
) -> tuple[int, int, dict[str, dict[str, int]]]:
    summaries: dict[str, dict[str, int]] = {}
    total_bytes = 0
    output_path.parent.mkdir(parents=True, exist_ok=True)

    with output_path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.writer(handle)
        writer.writerow(
            [
                "File Name",
                "Extension",
                "Size in Bytes",
                "Size in Human Readable",
                "Path From Root Folder",
                "SHA256 Hash",
            ]
        )

        if hashing:
            workers = max(2, os.cpu_count() or 2)
            with ThreadPoolExecutor(max_workers=workers) as pool:
                iterator = pool.map(hash_file, files)
                for index, (file_path, file_hash) in enumerate(zip(files, iterator), start=1):
                    stat = file_path.stat()
                    size = stat.st_size
                    total_bytes += size
                    ext = file_path.suffix.lower().lstrip(".")
                    summary_key = f".{ext}" if ext else "[no extension]"
                    bucket = summaries.setdefault(summary_key, {"count": 0, "bytes": 0})
                    bucket["count"] += 1
                    bucket["bytes"] += size

                    writer.writerow(
                        [
                            file_path.name,
                            ext,
                            size,
                            human_bytes(size),
                            file_path.relative_to(source_dir).as_posix(),
                            file_hash,
                        ]
                    )
                    if progress_callback:
                        progress_callback(index, len(files), file_path)
        else:
            for index, file_path in enumerate(files, start=1):
                stat = file_path.stat()
                size = stat.st_size
                total_bytes += size
                ext = file_path.suffix.lower().lstrip(".")
                summary_key = f".{ext}" if ext else "[no extension]"
                bucket = summaries.setdefault(summary_key, {"count": 0, "bytes": 0})
                bucket["count"] += 1
                bucket["bytes"] += size

                writer.writerow(
                    [
                        file_path.name,
                        ext,
                        size,
                        human_bytes(size),
                        file_path.relative_to(source_dir).as_posix(),
                        "",
                    ]
                )
                if progress_callback:
                    progress_callback(index, len(files), file_path)

    return len(files), total_bytes, summaries


def render_top(title: str, summaries: dict[str, dict[str, int]], key: str) -> list[str]:
    lines = [title]
    sorted_items = sorted(
        summaries.items(),
        key=lambda item: (item[1][key], item[1]["bytes"], item[0]),
        reverse=True,
    )[:8]
    for label, data in sorted_items:
        if key == "count":
            lines.append(f"  {label}: {data['count']} files, {human_bytes(data['bytes'])}")
        else:
            lines.append(f"  {label}: {human_bytes(data['bytes'])}, {data['count']} files")
    return lines


def run_cli(args: argparse.Namespace) -> int:
    source_dir = Path(args.source or prompt("Source folder", os.getcwd())).expanduser().resolve()
    if not source_dir.is_dir():
        print(f"Source folder does not exist: {source_dir}", file=sys.stderr)
        return 1

    output_dir = Path(args.output_dir or prompt("Output folder", str(source_dir))).expanduser().resolve()
    output_dir.mkdir(parents=True, exist_ok=True)

    output_name = args.output_name or prompt("Output file name", default_output_name(source_dir))
    if not output_name.lower().endswith(".csv"):
        print("Output file name must end in .csv", file=sys.stderr)
        return 1

    hashing = args.hashing or prompt_yes_no("Include SHA-256 hashes?", default=False)
    include_hidden = args.include_hidden or prompt_yes_no("Include hidden files?", default=False)
    include_system = args.include_system or prompt_yes_no("Include common system files?", default=False)
    exclude_raw = args.exclude_exts or prompt("Exclude extensions (comma-separated)", "")
    excluded_exts = normalize_exts(exclude_raw)

    output_path = output_dir / output_name
    if output_path.exists() and not args.overwrite:
        overwrite = prompt_yes_no(f"{output_path} already exists. Overwrite?", default=False)
        if not overwrite:
            print("Canceled.")
            return 1

    print("\nCollecting files...")
    started_at = time.time()
    files, filtered = collect_files(source_dir, include_hidden, include_system, excluded_exts)
    print(f"Found {len(files)} files to export.")

    print("Writing CSV...")
    file_count, total_bytes, summaries = write_report(source_dir, output_path, files, hashing)
    elapsed = time.time() - started_at

    print("\nDone")
    print(f"  Output: {output_path}")
    print(f"  Files: {file_count}")
    print(f"  Bytes: {total_bytes} ({human_bytes(total_bytes)})")
    print(f"  Filtered out: {filtered}")
    print(f"  Hashing: {'on' if hashing else 'off'}")
    print(f"  Elapsed: {elapsed:.2f}s")
    print()
    print("\n".join(render_top("Top extensions by count", summaries, "count")))
    print()
    print("\n".join(render_top("Top extensions by size", summaries, "bytes")))
    return 0


class ContentListApp:
    def __init__(self) -> None:
        self.root = tk.Tk()
        self.root.title("Content List Generator")
        self.root.geometry("980x720")
        self.root.minsize(860, 620)
        self.root.configure(bg="#f3f5f8")

        self.message_queue: queue.Queue[tuple[str, object]] = queue.Queue()
        self.running = False

        self.source_var = tk.StringVar(value=os.getcwd())
        self.output_dir_var = tk.StringVar(value=os.getcwd())
        self.output_name_var = tk.StringVar(value=default_output_name(Path(os.getcwd())))
        self.exclude_var = tk.StringVar(value="")
        self.hash_var = tk.BooleanVar(value=False)
        self.hidden_var = tk.BooleanVar(value=False)
        self.system_var = tk.BooleanVar(value=False)
        self.status_var = tk.StringVar(value="Ready.")
        self.progress_var = tk.DoubleVar(value=0)

        self.configure_style()
        self.build_ui()
        self.root.after(100, self.pump_queue)

    def configure_style(self) -> None:
        style = ttk.Style()
        if "clam" in style.theme_names():
            style.theme_use("clam")
        style.configure("App.TFrame", background="#f3f5f8")
        style.configure("Card.TFrame", background="#ffffff", relief="flat")
        style.configure("Title.TLabel", background="#f3f5f8", foreground="#12324a", font=("Segoe UI", 24, "bold"))
        style.configure("Body.TLabel", background="#ffffff", foreground="#243746", font=("Segoe UI", 11))
        style.configure("Hint.TLabel", background="#f3f5f8", foreground="#5b6b79", font=("Segoe UI", 10))
        style.configure("Primary.TButton", font=("Segoe UI", 11, "bold"))
        style.configure("Secondary.TButton", font=("Segoe UI", 10))
        style.configure("Modern.Horizontal.TProgressbar", troughcolor="#dde6ee", background="#2b7fff", bordercolor="#dde6ee")

    def build_ui(self) -> None:
        outer = ttk.Frame(self.root, style="App.TFrame", padding=24)
        outer.pack(fill="both", expand=True)

        header = ttk.Frame(outer, style="App.TFrame")
        header.pack(fill="x")
        ttk.Label(header, text="Content List Generator", style="Title.TLabel").pack(anchor="w")
        ttk.Label(
            header,
            text="Windows-friendly Python fallback with native folder pickers, filters, optional hashing, and live progress.",
            style="Hint.TLabel",
        ).pack(anchor="w", pady=(6, 18))

        card = ttk.Frame(outer, style="Card.TFrame", padding=20)
        card.pack(fill="both", expand=True)
        card.columnconfigure(1, weight=1)

        self.add_path_row(card, 0, "Source folder", self.source_var, self.choose_source)
        self.add_path_row(card, 1, "Output folder", self.output_dir_var, self.choose_output)
        self.add_entry_row(card, 2, "Output file name", self.output_name_var)
        self.add_entry_row(card, 3, "Exclude extensions", self.exclude_var, "Example: tmp,log,bak")

        options = ttk.Frame(card, style="Card.TFrame")
        options.grid(row=4, column=0, columnspan=3, sticky="ew", pady=(12, 4))
        ttk.Checkbutton(options, text="Include SHA-256 hashes", variable=self.hash_var).pack(anchor="w")
        ttk.Checkbutton(options, text="Include hidden files", variable=self.hidden_var).pack(anchor="w")
        ttk.Checkbutton(options, text="Include common system files", variable=self.system_var).pack(anchor="w")

        actions = ttk.Frame(card, style="Card.TFrame")
        actions.grid(row=5, column=0, columnspan=3, sticky="ew", pady=(16, 8))
        ttk.Button(actions, text="Generate CSV", style="Primary.TButton", command=self.start_scan).pack(side="left")
        ttk.Button(actions, text="Use Source As Output", style="Secondary.TButton", command=self.copy_source_to_output).pack(side="left", padx=(10, 0))

        self.progress = ttk.Progressbar(card, style="Modern.Horizontal.TProgressbar", variable=self.progress_var, mode="determinate")
        self.progress.grid(row=6, column=0, columnspan=3, sticky="ew", pady=(10, 8))
        ttk.Label(card, textvariable=self.status_var, style="Body.TLabel").grid(row=7, column=0, columnspan=3, sticky="w")

        ttk.Label(card, text="Summary", style="Body.TLabel").grid(row=8, column=0, sticky="w", pady=(18, 8))
        self.summary = tk.Text(card, height=16, wrap="word", bd=0, bg="#f7fafc", fg="#243746", font=("Consolas", 11))
        self.summary.grid(row=9, column=0, columnspan=3, sticky="nsew")
        card.rowconfigure(9, weight=1)

    def add_path_row(self, parent, row: int, label: str, variable: tk.StringVar, command) -> None:
        ttk.Label(parent, text=label, style="Body.TLabel").grid(row=row, column=0, sticky="w", pady=6, padx=(0, 12))
        entry = ttk.Entry(parent, textvariable=variable)
        entry.grid(row=row, column=1, sticky="ew", pady=6)
        ttk.Button(parent, text="Browse", style="Secondary.TButton", command=command).grid(row=row, column=2, padx=(12, 0), pady=6)

    def add_entry_row(self, parent, row: int, label: str, variable: tk.StringVar, hint: str = "") -> None:
        ttk.Label(parent, text=label, style="Body.TLabel").grid(row=row, column=0, sticky="w", pady=6, padx=(0, 12))
        entry = ttk.Entry(parent, textvariable=variable)
        entry.grid(row=row, column=1, columnspan=2, sticky="ew", pady=6)
        if hint:
            ttk.Label(parent, text=hint, style="Hint.TLabel").grid(row=row + 1, column=1, columnspan=2, sticky="w")

    def choose_source(self) -> None:
        chosen = filedialog.askdirectory(initialdir=self.source_var.get() or os.getcwd(), mustexist=True)
        if chosen:
            self.source_var.set(chosen)
            if not self.output_name_var.get().strip():
                self.output_name_var.set(default_output_name(Path(chosen)))

    def choose_output(self) -> None:
        chosen = filedialog.askdirectory(initialdir=self.output_dir_var.get() or os.getcwd(), mustexist=False)
        if chosen:
            self.output_dir_var.set(chosen)

    def copy_source_to_output(self) -> None:
        self.output_dir_var.set(self.source_var.get())

    def append_summary(self, text: str) -> None:
        self.summary.configure(state="normal")
        self.summary.delete("1.0", "end")
        self.summary.insert("end", text)
        self.summary.configure(state="disabled")

    def start_scan(self) -> None:
        if self.running:
            return

        source_dir = Path(self.source_var.get()).expanduser().resolve()
        output_dir = Path(self.output_dir_var.get()).expanduser().resolve()
        output_name = self.output_name_var.get().strip() or default_output_name(source_dir)
        excluded_exts = normalize_exts(self.exclude_var.get())

        if not source_dir.is_dir():
            messagebox.showerror("Invalid source folder", f"Source folder does not exist:\n{source_dir}")
            return
        if not output_name.lower().endswith(".csv"):
            messagebox.showerror("Invalid output file", "Output file name must end in .csv")
            return

        output_path = output_dir / output_name
        if output_path.exists():
            confirmed = messagebox.askyesno("Overwrite file?", f"{output_path}\n\nalready exists. Overwrite it?")
            if not confirmed:
                return

        self.running = True
        self.progress.configure(maximum=1)
        self.progress_var.set(0)
        self.status_var.set("Collecting files...")
        self.append_summary("Preparing scan...")

        thread = threading.Thread(
            target=self.run_scan_thread,
            args=(source_dir, output_path, excluded_exts),
            daemon=True,
        )
        thread.start()

    def run_scan_thread(self, source_dir: Path, output_path: Path, excluded_exts: set[str]) -> None:
        started = time.time()
        try:
            files, filtered = collect_files(
                source_dir,
                self.hidden_var.get(),
                self.system_var.get(),
                excluded_exts,
            )
            self.message_queue.put(("setup_progress", len(files)))
            self.message_queue.put(("status", f"Writing {len(files)} files to CSV..."))

            def on_progress(current: int, total: int, file_path: Path) -> None:
                self.message_queue.put(("progress", (current, total, file_path.name)))

            file_count, total_bytes, summaries = write_report(
                source_dir,
                output_path,
                files,
                self.hash_var.get(),
                progress_callback=on_progress,
            )
            elapsed = time.time() - started
            summary_lines = [
                "Done",
                f"Output: {output_path}",
                f"Files: {file_count}",
                f"Bytes: {total_bytes} ({human_bytes(total_bytes)})",
                f"Filtered out: {filtered}",
                f"Hashing: {'on' if self.hash_var.get() else 'off'}",
                f"Elapsed: {elapsed:.2f}s",
                "",
                *render_top("Top extensions by count", summaries, "count"),
                "",
                *render_top("Top extensions by size", summaries, "bytes"),
            ]
            self.message_queue.put(("done", "\n".join(summary_lines)))
        except Exception as exc:  # pragma: no cover
            self.message_queue.put(("error", str(exc)))

    def pump_queue(self) -> None:
        try:
            while True:
                kind, payload = self.message_queue.get_nowait()
                if kind == "setup_progress":
                    total = max(1, int(payload))
                    self.progress.configure(maximum=total)
                    self.progress_var.set(0)
                elif kind == "status":
                    self.status_var.set(str(payload))
                elif kind == "progress":
                    current, total, name = payload
                    self.progress.configure(maximum=max(1, total))
                    self.progress_var.set(current)
                    self.status_var.set(f"Processing {current}/{total}: {name}")
                elif kind == "done":
                    self.running = False
                    self.status_var.set("Complete.")
                    self.append_summary(str(payload))
                    self.progress_var.set(self.progress["maximum"])
                elif kind == "error":
                    self.running = False
                    self.status_var.set("Failed.")
                    messagebox.showerror("Scan failed", str(payload))
        except queue.Empty:
            pass
        self.root.after(100, self.pump_queue)

    def run(self) -> int:
        self.root.mainloop()
        return 0


def main() -> int:
    args = parse_args()
    has_explicit_cli_args = any(
        value
        for value in [
            args.source,
            args.output_dir,
            args.output_name,
            args.hashing,
            args.include_hidden,
            args.include_system,
            args.exclude_exts,
            args.overwrite,
        ]
    )

    if not args.cli and not has_explicit_cli_args and tk is not None:
        return ContentListApp().run()

    return run_cli(args)


if __name__ == "__main__":
    raise SystemExit(main())
