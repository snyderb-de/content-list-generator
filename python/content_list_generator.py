#!/usr/bin/env python3

from __future__ import annotations

import argparse
import os
import queue
import subprocess
import sys
import threading
from pathlib import Path

try:
    import tkinter as tk
    from tkinter import filedialog, messagebox, ttk
except Exception:  # pragma: no cover
    tk = None
    filedialog = None
    messagebox = None
    ttk = None

from content_list_core import EMAIL_EXTENSIONS, EmailCopyResult, build_scan_summary, collect_files, copy_email_files, default_output_name, normalize_exts, run_scan


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Recursive content list generator")
    parser.add_argument("--mode", choices=("scan", "email-copy"), default="scan")
    parser.add_argument("--source")
    parser.add_argument("--output-dir")
    parser.add_argument("--output-name")
    parser.add_argument("--dest")
    parser.add_argument("--hash", action="store_true", dest="hashing")
    parser.add_argument("--include-hidden", action="store_true")
    parser.add_argument("--include-system", action="store_true")
    parser.add_argument("--exclude-exts", default="")
    parser.add_argument("--overwrite", action="store_true")
    parser.add_argument("--xlsx", action="store_true", dest="create_xlsx")
    parser.add_argument("--preserve-zeros", action="store_true")
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


def open_in_file_manager(path: Path) -> None:
    target = path.expanduser().resolve()
    if sys.platform == "darwin":
        subprocess.run(["open", str(target)], check=False)
        return
    if os.name == "nt":
        os.startfile(str(target))  # type: ignore[attr-defined]
        return
    subprocess.run(["xdg-open", str(target)], check=False)




def run_cli_scan(args: argparse.Namespace) -> int:
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
    create_xlsx = args.create_xlsx or prompt_yes_no("Create XLSX after the CSV scan?", default=False)
    preserve_zeros = False
    if create_xlsx:
        preserve_zeros = args.preserve_zeros or prompt_yes_no("Preserve leading zeros in XLSX?", default=False)

    output_path = output_dir / output_name
    if output_path.exists() and not args.overwrite:
        overwrite = prompt_yes_no(f"{output_path} already exists. Overwrite?", default=False)
        if not overwrite:
            print("Canceled.")
            return 1

    print("\nCollecting files...")
    result = run_scan(
        source_dir,
        output_path,
        hashing=hashing,
        include_hidden=include_hidden,
        include_system=include_system,
        excluded_exts=excluded_exts,
        create_xlsx=create_xlsx,
        preserve_zeros=preserve_zeros,
    )
    print(build_scan_summary(result))
    return 0


def run_cli_email_copy(args: argparse.Namespace) -> int:
    source_raw = args.source or prompt("Source folder", str(Path.cwd()))
    dest_raw = args.dest or prompt("Destination folder")

    if not source_raw:
        print("Source folder is required.", file=sys.stderr)
        return 1
    if not dest_raw:
        print("Destination folder is required.", file=sys.stderr)
        return 1

    result = copy_email_files(
        Path(source_raw).expanduser().resolve(),
        Path(dest_raw).expanduser().resolve(),
    )
    print("\nDone")
    print(f"Source: {result.source_dir}")
    print(f"Destination: {result.dest_dir}")
    print(f"Copied: {result.copied}")
    print(f"Manifest: {result.manifest_path}")
    print("Extensions included:")
    print("  " + ", ".join(sorted(EMAIL_EXTENSIONS)))
    print("")
    print("Mode: preserve relative folders from the chosen source root")
    return 0


class EmailCopyWindow:
    def __init__(self, parent: "ContentListApp") -> None:
        self.parent = parent
        self.window = tk.Toplevel(parent.root)
        self.window.title("Copy Email Files")
        self.window.geometry("760x380")
        self.window.minsize(700, 340)
        self.window.configure(bg="#f3f5f8")
        self.window.transient(parent.root)
        self.window.grab_set()

        self.message_queue: queue.Queue[tuple[str, object]] = queue.Queue()
        self.running = False

        self.source_var = tk.StringVar(value=parent.source_var.get() or os.getcwd())
        self.dest_var = tk.StringVar(value=parent.output_dir_var.get() or os.getcwd())
        self.status_var = tk.StringVar(value="Choose the source and destination folders.")
        self.start_button: ttk.Button | None = None

        self.build_ui()
        self.window.after(100, self.pump_queue)

    def build_ui(self) -> None:
        outer = ttk.Frame(self.window, style="App.TFrame", padding=24)
        outer.pack(fill="both", expand=True)

        ttk.Label(outer, text="Copy Email Files", style="Title.TLabel").pack(anchor="w")
        ttk.Label(
            outer,
            text="This sub-window preserves the relative folder structure from the selected source root and writes a manifest report in the destination.",
            style="Hint.TLabel",
            wraplength=660,
            justify="left",
        ).pack(anchor="w", pady=(6, 18))

        card = ttk.Frame(outer, style="Card.TFrame", padding=20)
        card.pack(fill="both", expand=True)
        card.columnconfigure(1, weight=1)

        self.parent.add_path_row(card, 0, "Source folder", self.source_var, self.choose_source)
        self.parent.add_path_row(card, 1, "Destination folder", self.dest_var, self.choose_dest)

        ttk.Label(
            card,
            text="Included extensions: " + ", ".join(sorted(EMAIL_EXTENSIONS)),
            style="Body.TLabel",
            wraplength=620,
            justify="left",
        ).grid(row=2, column=0, columnspan=3, sticky="w", pady=(12, 14))

        actions = ttk.Frame(card, style="Card.TFrame")
        actions.grid(row=3, column=0, columnspan=3, sticky="w")
        self.start_button = ttk.Button(actions, text="Start Copy", style="Primary.TButton", command=self.start_copy)
        self.start_button.pack(side="left")
        ttk.Button(actions, text="Use Main Output Folder", style="Secondary.TButton", command=self.use_main_output).pack(side="left", padx=(10, 0))
        ttk.Button(actions, text="Cancel", style="Secondary.TButton", command=self.window.destroy).pack(side="left", padx=(10, 0))

        ttk.Label(card, textvariable=self.status_var, style="Body.TLabel", wraplength=620, justify="left").grid(
            row=4, column=0, columnspan=3, sticky="w", pady=(14, 0)
        )

    def choose_source(self) -> None:
        chosen = filedialog.askdirectory(initialdir=self.source_var.get() or os.getcwd(), mustexist=True)
        if chosen:
            self.source_var.set(chosen)
            self.status_var.set("Source selected. Now choose the destination folder.")

    def choose_dest(self) -> None:
        chosen = filedialog.askdirectory(initialdir=self.dest_var.get() or os.getcwd(), mustexist=False)
        if chosen:
            self.dest_var.set(chosen)
            self.status_var.set("Destination selected. Click Start Copy when you're ready.")

    def use_main_output(self) -> None:
        self.dest_var.set(self.parent.output_dir_var.get() or os.getcwd())
        self.status_var.set("Using the main window output folder as the destination.")

    def start_copy(self) -> None:
        if self.running:
            return

        source = Path(self.source_var.get()).expanduser().resolve()
        dest = Path(self.dest_var.get()).expanduser().resolve()
        if not source.is_dir():
            messagebox.showerror("Invalid source folder", f"Source folder does not exist:\n{source}")
            return

        self.running = True
        self.status_var.set("Copying email files...")
        if self.start_button is not None:
            self.start_button.configure(state="disabled")
        thread = threading.Thread(target=self.run_copy_thread, args=(source, dest), daemon=True)
        thread.start()

    def run_copy_thread(self, source: Path, dest: Path) -> None:
        try:
            result = copy_email_files(source, dest)
            self.message_queue.put(("done", result))
        except Exception as exc:  # pragma: no cover
            self.message_queue.put(("error", str(exc)))

    def pump_queue(self) -> None:
        try:
            while True:
                kind, payload = self.message_queue.get_nowait()
                if kind == "done":
                    self.running = False
                    if self.start_button is not None:
                        self.start_button.configure(state="normal")
                    result: EmailCopyResult = payload
                    self.parent.status_var.set(
                        f"Email copy complete. Copied {result.copied} files to {result.dest_dir}."
                    )
                    self.parent.last_email_result = result
                    self.parent.append_summary(
                        "\n".join(
                            [
                                "Email Copy Complete",
                                f"Source: {result.source_dir}",
                                f"Destination: {result.dest_dir}",
                                f"Manifest: {result.manifest_path}",
                                f"Copied: {result.copied}",
                                f"Elapsed: {result.elapsed:.2f}s",
                            ]
                        )
                    )
                    messagebox.showinfo(
                        "Done",
                        f"Copied {result.copied} files.\n\nDestination: {result.dest_dir}\nManifest: {result.manifest_path}",
                    )
                    self.window.destroy()
                    return
                if kind == "error":
                    self.running = False
                    if self.start_button is not None:
                        self.start_button.configure(state="normal")
                    self.status_var.set("Copy failed.")
                    messagebox.showerror("Copy failed", str(payload))
        except queue.Empty:
            pass
        if self.window.winfo_exists():
            self.window.after(100, self.pump_queue)


class ContentListApp:
    def __init__(self) -> None:
        self.root = tk.Tk()
        self.root.title("Content List Generator")
        self.root.geometry("1000x760")
        self.root.minsize(900, 660)
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
        self.xlsx_var = tk.BooleanVar(value=False)
        self.preserve_zeros_var = tk.BooleanVar(value=False)
        self.status_var = tk.StringVar(value="Ready.")
        self.progress_var = tk.DoubleVar(value=0)
        self.last_scan_output: Path | None = None
        self.last_scan_xlsx: Path | None = None
        self.last_email_result: EmailCopyResult | None = None
        self.generate_button: ttk.Button | None = None
        self.email_button: ttk.Button | None = None
        self.open_folder_button: ttk.Button | None = None
        self.open_latest_button: ttk.Button | None = None

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
            text="Windows-native Python app with scan and email-copy workflows, native pickers, optional XLSX export, and live progress.",
            style="Hint.TLabel",
        ).pack(anchor="w", pady=(6, 18))

        quick = ttk.Frame(outer, style="App.TFrame")
        quick.pack(fill="x", pady=(0, 12))
        ttk.Label(quick, text="Workflows", style="Body.TLabel").pack(anchor="w")
        ttk.Label(
            quick,
            text="Generate inventories from the main window or launch the dedicated email-copy sub-window.",
            style="Hint.TLabel",
        ).pack(anchor="w", pady=(4, 0))

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
        ttk.Checkbutton(options, text="Create XLSX after scan", variable=self.xlsx_var, command=self.sync_xlsx_state).pack(anchor="w")
        self.preserve_zeros_toggle = ttk.Checkbutton(
            options,
            text="Preserve leading zeros in XLSX",
            variable=self.preserve_zeros_var,
        )
        self.preserve_zeros_toggle.pack(anchor="w")

        actions = ttk.Frame(card, style="Card.TFrame")
        actions.grid(row=5, column=0, columnspan=3, sticky="ew", pady=(16, 8))
        self.generate_button = ttk.Button(actions, text="Generate Content List", style="Primary.TButton", command=self.start_scan)
        self.generate_button.pack(side="left")
        self.email_button = ttk.Button(actions, text="Copy Email Files", style="Secondary.TButton", command=self.open_email_copy_window)
        self.email_button.pack(side="left", padx=(10, 0))
        ttk.Button(actions, text="Use Source As Output", style="Secondary.TButton", command=self.copy_source_to_output).pack(side="left", padx=(10, 0))
        self.open_folder_button = ttk.Button(actions, text="Open Output Folder", style="Secondary.TButton", command=self.open_output_folder)
        self.open_folder_button.pack(side="left", padx=(10, 0))
        self.open_latest_button = ttk.Button(actions, text="Open Latest Result", style="Secondary.TButton", command=self.open_latest_result)
        self.open_latest_button.pack(side="left", padx=(10, 0))

        self.progress = ttk.Progressbar(card, style="Modern.Horizontal.TProgressbar", variable=self.progress_var, mode="determinate")
        self.progress.grid(row=6, column=0, columnspan=3, sticky="ew", pady=(10, 8))
        ttk.Label(card, textvariable=self.status_var, style="Body.TLabel").grid(row=7, column=0, columnspan=3, sticky="w")

        ttk.Label(card, text="Summary", style="Body.TLabel").grid(row=8, column=0, sticky="w", pady=(18, 8))
        self.summary = tk.Text(card, height=16, wrap="word", bd=0, bg="#f7fafc", fg="#243746", font=("Consolas", 11))
        self.summary.grid(row=9, column=0, columnspan=3, sticky="nsew")
        card.rowconfigure(9, weight=1)

        self.sync_xlsx_state()
        self.sync_action_buttons()

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

    def sync_xlsx_state(self) -> None:
        state = "normal" if self.xlsx_var.get() else "disabled"
        self.preserve_zeros_toggle.configure(state=state)
        if not self.xlsx_var.get():
            self.preserve_zeros_var.set(False)

    def sync_action_buttons(self) -> None:
        running_state = "disabled" if self.running else "normal"
        if self.generate_button is not None:
            self.generate_button.configure(state=running_state)
        if self.email_button is not None:
            self.email_button.configure(state=running_state)
        if self.open_folder_button is not None:
            self.open_folder_button.configure(state="normal")
        if self.open_latest_button is not None:
            has_latest = self.last_scan_output is not None or self.last_email_result is not None
            self.open_latest_button.configure(state="normal" if has_latest else "disabled")

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

    def open_email_copy_window(self) -> None:
        if self.running:
            return
        EmailCopyWindow(self)

    def open_output_folder(self) -> None:
        open_in_file_manager(Path(self.output_dir_var.get() or os.getcwd()))

    def open_latest_result(self) -> None:
        if self.last_scan_xlsx is not None and self.last_scan_xlsx.exists():
            open_in_file_manager(self.last_scan_xlsx)
            return
        if self.last_scan_output is not None and self.last_scan_output.exists():
            open_in_file_manager(self.last_scan_output)
            return
        if self.last_email_result is not None:
            open_in_file_manager(self.last_email_result.dest_dir)

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
        self.sync_action_buttons()
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
        try:
            files, *_ = collect_files(
                source_dir,
                self.hidden_var.get(),
                self.system_var.get(),
                excluded_exts,
            )
            self.message_queue.put(("setup_progress", len(files)))
            self.message_queue.put(("status", f"Writing {len(files)} files to CSV..."))

            def on_progress(current: int, total: int, file_path: Path) -> None:
                self.message_queue.put(("progress", (current, total, file_path.name)))

            result = run_scan(
                source_dir,
                output_path,
                hashing=self.hash_var.get(),
                include_hidden=self.hidden_var.get(),
                include_system=self.system_var.get(),
                excluded_exts=excluded_exts,
                create_xlsx=self.xlsx_var.get(),
                preserve_zeros=self.preserve_zeros_var.get(),
                progress_callback=on_progress,
            )
            self.message_queue.put(("done", result))
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
                    result = payload
                    self.last_scan_output = result.output_path
                    self.last_scan_xlsx = result.xlsx_path
                    self.status_var.set("Complete.")
                    self.append_summary(build_scan_summary(result))
                    self.progress_var.set(self.progress["maximum"])
                    self.sync_action_buttons()
                elif kind == "error":
                    self.running = False
                    self.status_var.set("Failed.")
                    self.sync_action_buttons()
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
            args.dest,
            args.hashing,
            args.include_hidden,
            args.include_system,
            args.exclude_exts,
            args.overwrite,
            args.create_xlsx,
            args.preserve_zeros,
            args.mode != "scan",
        ]
    )

    if not args.cli and not has_explicit_cli_args and tk is not None:
        return ContentListApp().run()

    if args.mode == "email-copy":
        return run_cli_email_copy(args)
    return run_cli_scan(args)


if __name__ == "__main__":
    raise SystemExit(main())
