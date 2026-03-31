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

        content = ttk.Frame(outer, style="App.TFrame")
        content.pack(fill="both", expand=True)
        content.columnconfigure(0, weight=5)
        content.columnconfigure(1, weight=3)
        content.rowconfigure(0, weight=1)

        card = ttk.Frame(content, style="Card.TFrame", padding=20)
        card.grid(row=0, column=0, sticky="nsew", padx=(0, 12))
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
        self.parent.latest_status_var.set("Last action: email copy in progress")
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
                    self.parent.latest_status_var.set("Last action: email copy completed")
                    self.parent.set_activity(
                        "Email copy completed",
                        f"Copied {result.copied} files into {result.dest_dir}.\nManifest: {result.manifest_path}",
                    )
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
                    self.parent.latest_status_var.set("Last action: email copy failed")
                    messagebox.showerror("Copy failed", str(payload))
        except queue.Empty:
            pass
        if self.window.winfo_exists():
            self.window.after(100, self.pump_queue)


class ContentListApp:
    def __init__(self) -> None:
        self.root = tk.Tk()
        self.root.title("Content List Generator")
        self.root.geometry("1220x820")
        self.root.minsize(1040, 720)
        self.root.configure(bg="#eef3f7")

        self.message_queue: queue.Queue[tuple[str, object]] = queue.Queue()
        self.running = False

        cwd = Path(os.getcwd())
        self.source_var = tk.StringVar(value=str(cwd))
        self.output_dir_var = tk.StringVar(value=str(cwd))
        self.output_name_var = tk.StringVar(value=default_output_name(cwd))
        self.exclude_var = tk.StringVar(value="")
        self.hash_var = tk.BooleanVar(value=False)
        self.hidden_var = tk.BooleanVar(value=False)
        self.system_var = tk.BooleanVar(value=False)
        self.xlsx_var = tk.BooleanVar(value=False)
        self.preserve_zeros_var = tk.BooleanVar(value=False)
        self.status_var = tk.StringVar(value="Ready.")
        self.progress_var = tk.DoubleVar(value=0)
        self.activity_title_var = tk.StringVar(value="No activity yet.")
        self.activity_detail_var = tk.StringVar(
            value="Run a content-list scan or open the email-copy window to create your first result."
        )
        self.latest_scan_var = tk.StringVar(value="Latest CSV: none")
        self.latest_xlsx_var = tk.StringVar(value="Latest XLSX: none")
        self.latest_manifest_var = tk.StringVar(value="Latest manifest: none")
        self.latest_status_var = tk.StringVar(value="Last action: none")
        self.last_scan_output: Path | None = None
        self.last_scan_xlsx: Path | None = None
        self.last_email_result: EmailCopyResult | None = None
        self.generate_button: ttk.Button | None = None
        self.email_button: ttk.Button | None = None
        self.open_folder_button: ttk.Button | None = None
        self.open_latest_button: ttk.Button | None = None
        self.open_scan_button: ttk.Button | None = None
        self.open_xlsx_button: ttk.Button | None = None
        self.open_manifest_button: ttk.Button | None = None

        self.configure_style()
        self.build_ui()
        self.root.after(100, self.pump_queue)

    def configure_style(self) -> None:
        style = ttk.Style()
        if "clam" in style.theme_names():
            style.theme_use("clam")
        style.configure("App.TFrame", background="#eef3f7")
        style.configure("Hero.TFrame", background="#14324a")
        style.configure("Card.TFrame", background="#ffffff", relief="flat")
        style.configure("Panel.TFrame", background="#f6f9fc", relief="flat")
        style.configure("Title.TLabel", background="#eef3f7", foreground="#12324a", font=("Segoe UI", 26, "bold"))
        style.configure("HeroTitle.TLabel", background="#14324a", foreground="#ffffff", font=("Segoe UI", 24, "bold"))
        style.configure("HeroBody.TLabel", background="#14324a", foreground="#d7e5f2", font=("Segoe UI", 11))
        style.configure("Body.TLabel", background="#ffffff", foreground="#243746", font=("Segoe UI", 11))
        style.configure("Panel.TLabel", background="#f6f9fc", foreground="#243746", font=("Segoe UI", 11))
        style.configure("Hint.TLabel", background="#eef3f7", foreground="#5b6b79", font=("Segoe UI", 10))
        style.configure("CardHint.TLabel", background="#ffffff", foreground="#5b6b79", font=("Segoe UI", 10))
        style.configure("PanelHint.TLabel", background="#f6f9fc", foreground="#607282", font=("Segoe UI", 10))
        style.configure("MetricValue.TLabel", background="#ffffff", foreground="#12324a", font=("Segoe UI", 18, "bold"))
        style.configure("MetricLabel.TLabel", background="#ffffff", foreground="#607282", font=("Segoe UI", 9))
        style.configure("Primary.TButton", font=("Segoe UI", 11, "bold"))
        style.configure("Secondary.TButton", font=("Segoe UI", 10))
        style.configure("Modern.Horizontal.TProgressbar", troughcolor="#dde6ee", background="#2b7fff", bordercolor="#dde6ee")

    def build_ui(self) -> None:
        outer = ttk.Frame(self.root, style="App.TFrame", padding=24)
        outer.pack(fill="both", expand=True)
        outer.columnconfigure(0, weight=4)
        outer.columnconfigure(1, weight=2)
        outer.rowconfigure(2, weight=1)

        hero = ttk.Frame(outer, style="Hero.TFrame", padding=22)
        hero.grid(row=0, column=0, columnspan=2, sticky="ew")
        ttk.Label(hero, text="Content List Generator", style="HeroTitle.TLabel").pack(anchor="w")
        ttk.Label(
            hero,
            text=(
                "Desktop workflow for recursive content-list scans and email-file copy jobs. "
                "Use the main window for inventory exports and launch the dedicated email-copy flow when needed."
            ),
            style="HeroBody.TLabel",
            wraplength=1040,
            justify="left",
        ).pack(anchor="w", pady=(8, 0))

        metrics = ttk.Frame(outer, style="App.TFrame")
        metrics.grid(row=1, column=0, columnspan=2, sticky="ew", pady=(16, 16))
        for column in range(4):
            metrics.columnconfigure(column, weight=1)
        self.build_metric_card(metrics, 0, "Inventory", "CSV first, XLSX optional")
        self.build_metric_card(metrics, 1, "Email Copy", "Preserve relative folders")
        self.build_metric_card(metrics, 2, "Quick Access", "Open latest results")
        self.build_metric_card(metrics, 3, "Cross-Platform", "Windows GUI, Go GUI/TUI")

        main_card = ttk.Frame(outer, style="Card.TFrame", padding=22)
        main_card.grid(row=2, column=0, sticky="nsew", padx=(0, 12))
        main_card.columnconfigure(1, weight=1)
        main_card.rowconfigure(8, weight=1)

        ttk.Label(main_card, text="Scan Workflow", style="Body.TLabel").grid(row=0, column=0, sticky="w")
        ttk.Label(
            main_card,
            text="Choose the source and output settings below, then generate the content list.",
            style="CardHint.TLabel",
        ).grid(row=1, column=0, columnspan=3, sticky="w", pady=(4, 14))

        self.add_path_row(main_card, 2, "Source folder", self.source_var, self.choose_source)
        self.add_path_row(main_card, 3, "Output folder", self.output_dir_var, self.choose_output)
        self.add_entry_row(main_card, 4, "Output file name", self.output_name_var)
        self.add_entry_row(main_card, 5, "Exclude extensions", self.exclude_var, "Example: tmp,log,bak")

        options = ttk.Frame(main_card, style="Card.TFrame")
        options.grid(row=6, column=0, columnspan=3, sticky="ew", pady=(14, 6))
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

        actions = ttk.Frame(main_card, style="Card.TFrame")
        actions.grid(row=7, column=0, columnspan=3, sticky="ew", pady=(16, 10))
        self.generate_button = ttk.Button(actions, text="Generate Content List", style="Primary.TButton", command=self.start_scan)
        self.generate_button.pack(side="left")
        self.email_button = ttk.Button(actions, text="Copy Email Files", style="Secondary.TButton", command=self.open_email_copy_window)
        self.email_button.pack(side="left", padx=(10, 0))
        ttk.Button(actions, text="Use Source As Output", style="Secondary.TButton", command=self.copy_source_to_output).pack(side="left", padx=(10, 0))
        self.open_folder_button = ttk.Button(actions, text="Open Output Folder", style="Secondary.TButton", command=self.open_output_folder)
        self.open_folder_button.pack(side="left", padx=(10, 0))
        self.open_latest_button = ttk.Button(actions, text="Open Latest Result", style="Secondary.TButton", command=self.open_latest_result)
        self.open_latest_button.pack(side="left", padx=(10, 0))

        self.progress = ttk.Progressbar(main_card, style="Modern.Horizontal.TProgressbar", variable=self.progress_var, mode="determinate")
        self.progress.grid(row=8, column=0, columnspan=3, sticky="ew", pady=(0, 8))
        ttk.Label(main_card, textvariable=self.status_var, style="Body.TLabel").grid(row=9, column=0, columnspan=3, sticky="w")

        ttk.Label(main_card, text="Detailed Summary", style="Body.TLabel").grid(row=10, column=0, sticky="w", pady=(18, 8))
        self.summary = tk.Text(main_card, height=16, wrap="word", bd=0, bg="#f7fafc", fg="#243746", font=("Consolas", 11))
        self.summary.grid(row=11, column=0, columnspan=3, sticky="nsew")
        main_card.rowconfigure(11, weight=1)

        side = ttk.Frame(outer, style="Panel.TFrame", padding=20)
        side.grid(row=2, column=1, sticky="nsew")
        side.columnconfigure(0, weight=1)

        ttk.Label(side, text="Latest Activity", style="Panel.TLabel").grid(row=0, column=0, sticky="w")
        ttk.Label(side, textvariable=self.activity_title_var, style="Panel.TLabel", wraplength=300, justify="left").grid(
            row=1, column=0, sticky="w", pady=(10, 6)
        )
        ttk.Label(side, textvariable=self.activity_detail_var, style="PanelHint.TLabel", wraplength=300, justify="left").grid(
            row=2, column=0, sticky="w"
        )

        latest = ttk.Frame(side, style="Panel.TFrame")
        latest.grid(row=3, column=0, sticky="ew", pady=(18, 8))
        ttk.Label(latest, textvariable=self.latest_status_var, style="Panel.TLabel", wraplength=300, justify="left").pack(anchor="w")
        ttk.Label(latest, textvariable=self.latest_scan_var, style="PanelHint.TLabel", wraplength=300, justify="left").pack(anchor="w", pady=(8, 0))
        ttk.Label(latest, textvariable=self.latest_xlsx_var, style="PanelHint.TLabel", wraplength=300, justify="left").pack(anchor="w", pady=(6, 0))
        ttk.Label(latest, textvariable=self.latest_manifest_var, style="PanelHint.TLabel", wraplength=300, justify="left").pack(anchor="w", pady=(6, 0))

        quick_actions = ttk.Frame(side, style="Panel.TFrame")
        quick_actions.grid(row=4, column=0, sticky="ew", pady=(18, 10))
        ttk.Label(quick_actions, text="Quick Open", style="Panel.TLabel").pack(anchor="w")
        self.open_scan_button = ttk.Button(quick_actions, text="Open Latest CSV", style="Secondary.TButton", command=self.open_latest_csv)
        self.open_scan_button.pack(fill="x", pady=(10, 0))
        self.open_xlsx_button = ttk.Button(quick_actions, text="Open Latest XLSX", style="Secondary.TButton", command=self.open_latest_xlsx)
        self.open_xlsx_button.pack(fill="x", pady=(8, 0))
        self.open_manifest_button = ttk.Button(quick_actions, text="Open Latest Manifest", style="Secondary.TButton", command=self.open_latest_manifest)
        self.open_manifest_button.pack(fill="x", pady=(8, 0))

        tips = ttk.Frame(side, style="Panel.TFrame")
        tips.grid(row=5, column=0, sticky="ew", pady=(18, 0))
        ttk.Label(tips, text="Workflow Notes", style="Panel.TLabel").pack(anchor="w")
        ttk.Label(
            tips,
            text=(
                "Use this main window for inventory scans. Open the email-copy window when you want "
                "a dedicated source-to-destination flow with a manifest report."
            ),
            style="PanelHint.TLabel",
            wraplength=300,
            justify="left",
        ).pack(anchor="w", pady=(8, 0))

        self.sync_xlsx_state()
        self.sync_action_buttons()
        self.sync_result_buttons()

    def build_metric_card(self, parent, column: int, label: str, value: str) -> None:
        card = ttk.Frame(parent, style="Card.TFrame", padding=16)
        card.grid(row=0, column=column, sticky="ew", padx=(0 if column == 0 else 8, 0))
        ttk.Label(card, text=label, style="MetricValue.TLabel").pack(anchor="w")
        ttk.Label(card, text=value, style="MetricLabel.TLabel").pack(anchor="w", pady=(6, 0))

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

    def sync_result_buttons(self) -> None:
        if self.open_scan_button is not None:
            has_csv = self.last_scan_output is not None and self.last_scan_output.exists()
            self.open_scan_button.configure(state="normal" if has_csv else "disabled")
        if self.open_xlsx_button is not None:
            has_xlsx = self.last_scan_xlsx is not None and self.last_scan_xlsx.exists()
            self.open_xlsx_button.configure(state="normal" if has_xlsx else "disabled")
        if self.open_manifest_button is not None:
            has_manifest = self.last_email_result is not None and self.last_email_result.manifest_path.exists()
            self.open_manifest_button.configure(state="normal" if has_manifest else "disabled")

    def set_activity(self, title: str, detail: str) -> None:
        self.activity_title_var.set(title)
        self.activity_detail_var.set(detail)
        self.sync_result_buttons()
        self.refresh_latest_labels()

    def refresh_latest_labels(self) -> None:
        self.latest_scan_var.set(f"Latest CSV: {self.last_scan_output if self.last_scan_output else 'none'}")
        self.latest_xlsx_var.set(f"Latest XLSX: {self.last_scan_xlsx if self.last_scan_xlsx else 'none'}")
        manifest = self.last_email_result.manifest_path if self.last_email_result is not None else None
        self.latest_manifest_var.set(f"Latest manifest: {manifest if manifest else 'none'}")

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

    def open_latest_csv(self) -> None:
        if self.last_scan_output is not None:
            open_in_file_manager(self.last_scan_output)

    def open_latest_xlsx(self) -> None:
        if self.last_scan_xlsx is not None:
            open_in_file_manager(self.last_scan_xlsx)

    def open_latest_manifest(self) -> None:
        if self.last_email_result is not None:
            open_in_file_manager(self.last_email_result.manifest_path)

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
        self.latest_status_var.set("Last action: scan in progress")
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
                    self.set_activity(
                        "Content list scan completed",
                        f"CSV: {result.output_path}\nXLSX: {result.xlsx_path if result.xlsx_path else 'not created'}\nFiles: {result.files}",
                    )
                    self.status_var.set("Complete.")
                    self.latest_status_var.set("Last action: content-list scan completed")
                    self.append_summary(build_scan_summary(result))
                    self.progress_var.set(self.progress["maximum"])
                    self.sync_action_buttons()
                    self.sync_result_buttons()
                elif kind == "error":
                    self.running = False
                    self.status_var.set("Failed.")
                    self.latest_status_var.set("Last action: scan failed")
                    self.sync_action_buttons()
                    self.sync_result_buttons()
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
