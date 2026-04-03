#!/usr/bin/env python3

from __future__ import annotations

import argparse
import json
import os
import queue
import subprocess
import sys
import threading
import webbrowser
from pathlib import Path

try:
    import tkinter as tk
    from tkinter import filedialog, messagebox, ttk
except Exception:  # pragma: no cover
    tk = None
    filedialog = None
    messagebox = None
    ttk = None

from content_list_core import (
    EMAIL_EXTENSIONS,
    EmailCopyProgress,
    EmailCopyResult,
    build_scan_summary,
    collect_files,
    copy_email_files,
    default_output_name,
    normalize_exts,
    run_scan,
)


PLACEHOLDER_GITHUB_URL = "https://github.com/placeholder/content-list-generator"
SETTINGS_PATH = Path.home() / ".content-list-generator-settings.json"


def load_theme_mode() -> str:
    try:
        data = json.loads(SETTINGS_PATH.read_text(encoding="utf-8"))
    except (OSError, ValueError, TypeError):
        return "light"
    if not isinstance(data, dict):
        return "light"
    return "dark" if str(data.get("appearance_mode", "")).lower() == "dark" else "light"


def save_theme_mode(mode: str) -> None:
    try:
        data = json.loads(SETTINGS_PATH.read_text(encoding="utf-8"))
        if not isinstance(data, dict):
            data = {}
    except (OSError, ValueError, TypeError):
        data = {}
    data["appearance_mode"] = "dark" if mode == "dark" else "light"
    try:
        SETTINGS_PATH.write_text(json.dumps(data, indent=2), encoding="utf-8")
    except OSError:
        return


def palette_for_mode(mode: str) -> dict[str, str]:
    if mode == "dark":
        return {
            "app_bg": "#10171f",
            "hero_bg": "#0c1621",
            "card_bg": "#18222d",
            "card_alt_bg": "#101a24",
            "title_fg": "#edf4fb",
            "hero_fg": "#f5f9fd",
            "hero_muted": "#b9cada",
            "body_fg": "#e3edf5",
            "hint_fg": "#9fb2c3",
            "entry_bg": "#101821",
            "entry_fg": "#edf4fb",
            "border": "#2b3947",
            "progress_trough": "#273644",
            "progress_fill": "#5aa2ff",
            "primary_bg": "#2f7ff1",
            "primary_fg": "#f8fbff",
            "secondary_bg": "#233242",
            "secondary_fg": "#edf4fb",
            "selection_bg": "#2a4a68",
            "selection_fg": "#f8fbff",
        }
    return {
        "app_bg": "#eef3f7",
        "hero_bg": "#14324a",
        "card_bg": "#ffffff",
        "card_alt_bg": "#f7fafc",
        "title_fg": "#12324a",
        "hero_fg": "#ffffff",
        "hero_muted": "#d7e5f2",
        "body_fg": "#243746",
        "hint_fg": "#5b6b79",
        "entry_bg": "#ffffff",
        "entry_fg": "#243746",
        "border": "#d8e1e8",
        "progress_trough": "#dde6ee",
        "progress_fill": "#2b7fff",
        "primary_bg": "#2b7fff",
        "primary_fg": "#ffffff",
        "secondary_bg": "#ffffff",
        "secondary_fg": "#243746",
        "selection_bg": "#d8e8ff",
        "selection_fg": "#12324a",
    }


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


def choose_directory(parent, title: str, initialdir: str, mustexist: bool, colors: dict[str, str] | None = None) -> str:
    if tk is None or ttk is None:
        return filedialog.askdirectory(
            parent=parent,
            title=title,
            initialdir=initialdir or os.getcwd(),
            mustexist=mustexist,
        )
    return FolderPickerDialog(parent, title, initialdir or os.getcwd(), mustexist, colors or palette_for_mode("light")).show()


def folder_places() -> list[tuple[str, Path]]:
    places: list[tuple[str, Path]] = []

    def add_place(label: str, path: Path) -> None:
        try:
            resolved = path.expanduser().resolve()
        except Exception:
            return
        if not resolved.is_dir():
            return
        if any(existing == resolved for _, existing in places):
            return
        places.append((label, resolved))

    home = Path.home()
    add_place("Home", home)
    add_place("Desktop", home / "Desktop")
    add_place("Documents", home / "Documents")
    add_place("Downloads", home / "Downloads")
    add_place("Computer", Path("/"))

    if sys.platform == "darwin":
        volumes = Path("/Volumes")
        if volumes.is_dir():
            for entry in sorted(volumes.iterdir(), key=lambda item: item.name.lower()):
                if entry.is_dir() and not entry.name.startswith("."):
                    add_place(entry.name, entry)
    else:
        for root in (Path("/media"), Path("/run/media"), Path("/mnt")):
            if not root.is_dir():
                continue
            for entry in sorted(root.iterdir(), key=lambda item: item.name.lower()):
                if not entry.is_dir():
                    continue
                add_place(entry.name, entry)
                for sub in sorted(entry.iterdir(), key=lambda item: item.name.lower()):
                    if sub.is_dir():
                        add_place(sub.name, sub)

    return places


def folder_children(path: Path) -> list[tuple[str, Path, str]]:
    items: list[tuple[str, Path, str]] = []
    if path.parent != path:
        parent_name = path.parent.name or str(path.parent)
        items.append(("(Parent)", path.parent, f"Back to {parent_name}"))

    try:
        entries = sorted(path.iterdir(), key=lambda item: item.name.lower())
    except OSError:
        return items

    for entry in entries:
        if not entry.is_dir() or entry.name.startswith("."):
            continue
        subtitle = "Restricted access"
        try:
            visible = [child for child in entry.iterdir() if not child.name.startswith(".")]
            subtitle = f"{len(visible)} items"
        except OSError:
            pass
        items.append((entry.name, entry, subtitle))
    return items


def breadcrumb_text(path: Path) -> str:
    if sys.platform == "darwin" and path.parts[:2] == ("/", "Volumes"):
        return "Volumes  >  " + "  >  ".join(path.parts[2:])
    if path == Path("/"):
        return "/"
    return "  >  ".join(part for part in path.parts if part and part != "/")


class FolderPickerDialog:
    def __init__(self, parent, title: str, initialdir: str, mustexist: bool, colors: dict[str, str]) -> None:
        self.parent = parent
        self.title = title
        self.mustexist = mustexist
        self.colors = colors
        self.result = ""
        self.current_path = Path(initialdir or os.getcwd()).expanduser()
        if not self.current_path.exists():
            self.current_path = self.current_path.parent
        if not self.current_path.is_dir():
            self.current_path = Path.home()

        self.window = tk.Toplevel(parent)
        self.window.title("Content List Generator")
        self.window.geometry("1180x840")
        self.window.minsize(980, 720)
        self.window.configure(bg=self.colors["app_bg"])
        self.window.transient(parent)
        self.window.grab_set()

        self.path_var = tk.StringVar(value=str(self.current_path))
        self.footer_var = tk.StringVar(value=f"Current selected folder: {self.current_path}")

        self.place_list: tk.Listbox | None = None
        self.folder_list: tk.Listbox | None = None
        self.folder_details: list[tuple[str, Path, str]] = []
        self.places = folder_places()

        self.build_ui()
        self.refresh_lists()
        self.window.after(50, self.focus_folder_list)

    def build_ui(self) -> None:
        shell = ttk.Frame(self.window, style="App.TFrame", padding=24)
        shell.pack(fill="both", expand=True)
        shell.columnconfigure(1, weight=1)
        shell.rowconfigure(2, weight=1)

        ttk.Label(shell, text="Content List Generator", style="Title.TLabel").grid(row=0, column=0, columnspan=2, sticky="w")

        top_bar = ttk.Frame(shell, style="Card.TFrame", padding=18)
        top_bar.grid(row=1, column=0, columnspan=2, sticky="ew", pady=(18, 0))
        top_bar.columnconfigure(0, weight=1)
        ttk.Label(top_bar, textvariable=self.path_var, style="Body.TLabel", wraplength=760, justify="left").grid(row=0, column=0, sticky="w")
        actions = ttk.Frame(top_bar, style="Card.TFrame")
        actions.grid(row=0, column=1, sticky="e")
        ttk.Button(actions, text="Up", style="Secondary.TButton", command=self.go_up).pack(side="left")
        ttk.Button(actions, text="New Folder", style="Secondary.TButton", command=self.new_folder).pack(side="left", padx=(10, 0))

        side = ttk.Frame(shell, style="Card.TFrame", padding=18)
        side.grid(row=2, column=0, sticky="nsw", pady=(14, 0))
        side.columnconfigure(0, weight=1)
        ttk.Label(side, text="LOCATIONS", style="Body.TLabel").grid(row=0, column=0, sticky="w")
        ttk.Label(side, text="Places", style="CardHint.TLabel").grid(row=1, column=0, sticky="w", pady=(2, 14))
        self.place_list = tk.Listbox(side, activestyle="none", exportselection=False, height=18, bd=0, highlightthickness=0, font=("Segoe UI", 14))
        self.place_list.configure(
            bg=self.colors["card_bg"],
            fg=self.colors["body_fg"],
            selectbackground=self.colors["selection_bg"],
            selectforeground=self.colors["selection_fg"],
            highlightbackground=self.colors["border"],
        )
        self.place_list.grid(row=2, column=0, sticky="nsew")
        self.place_list.bind("<<ListboxSelect>>", self.on_place_select)

        main = ttk.Frame(shell, style="Card.TFrame", padding=18)
        main.grid(row=2, column=1, sticky="nsew", padx=(14, 0), pady=(14, 0))
        main.columnconfigure(0, weight=1)
        main.rowconfigure(0, weight=1)
        self.folder_list = tk.Listbox(main, activestyle="none", exportselection=False, bd=0, highlightthickness=0, font=("Segoe UI", 15), selectmode="browse")
        self.folder_list.configure(
            bg=self.colors["card_bg"],
            fg=self.colors["body_fg"],
            selectbackground=self.colors["selection_bg"],
            selectforeground=self.colors["selection_fg"],
            highlightbackground=self.colors["border"],
        )
        self.folder_list.grid(row=0, column=0, sticky="nsew")
        self.folder_list.bind("<<ListboxSelect>>", self.on_folder_select)
        self.folder_list.bind("<Double-Button-1>", self.on_folder_activate)

        footer = ttk.Frame(shell, style="Card.TFrame", padding=18)
        footer.grid(row=3, column=0, columnspan=2, sticky="ew", pady=(14, 0))
        footer.columnconfigure(0, weight=1)
        ttk.Label(footer, textvariable=self.footer_var, style="Body.TLabel", wraplength=900, justify="left").grid(row=0, column=0, sticky="w")
        footer_actions = ttk.Frame(footer, style="Card.TFrame")
        footer_actions.grid(row=0, column=1, sticky="e")
        ttk.Button(footer_actions, text="Cancel", style="Secondary.TButton", command=self.cancel).pack(side="left")
        ttk.Button(footer_actions, text="Open", style="Primary.TButton", command=self.open).pack(side="left", padx=(10, 0))

    def focus_folder_list(self) -> None:
        if self.folder_list is not None and self.folder_list.winfo_exists():
            self.folder_list.focus_force()

    def refresh_lists(self) -> None:
        self.path_var.set(breadcrumb_text(self.current_path))
        self.footer_var.set(f"Current selected folder: {self.current_path}")

        if self.place_list is not None:
            self.place_list.delete(0, "end")
            for label, _ in self.places:
                self.place_list.insert("end", label)
            best_index = -1
            best_length = -1
            for index, (_, path) in enumerate(self.places):
                try:
                    self.current_path.relative_to(path)
                    if len(str(path)) > best_length:
                        best_index = index
                        best_length = len(str(path))
                except ValueError:
                    continue
            if best_index >= 0:
                self.place_list.selection_clear(0, "end")
                self.place_list.selection_set(best_index)

        self.folder_details = folder_children(self.current_path)
        if self.folder_list is not None:
            self.folder_list.delete(0, "end")
            for name, _, subtitle in self.folder_details:
                self.folder_list.insert("end", f"{name}\n   {subtitle}")

    def on_place_select(self, _event=None) -> None:
        if self.place_list is None:
            return
        selection = self.place_list.curselection()
        if not selection:
            return
        _, path = self.places[selection[0]]
        self.current_path = path
        self.refresh_lists()

    def on_folder_select(self, _event=None) -> None:
        if self.folder_list is None:
            return
        selection = self.folder_list.curselection()
        if not selection:
            self.footer_var.set(f"Current selected folder: {self.current_path}")
            return
        _, path, _ = self.folder_details[selection[0]]
        self.footer_var.set(f"Current selected folder: {path}")

    def on_folder_activate(self, _event=None) -> None:
        if self.folder_list is None:
            return
        selection = self.folder_list.curselection()
        if not selection:
            return
        _, path, _ = self.folder_details[selection[0]]
        self.current_path = path
        self.refresh_lists()

    def go_up(self) -> None:
        if self.current_path.parent != self.current_path:
            self.current_path = self.current_path.parent
            self.refresh_lists()

    def new_folder(self) -> None:
        entry_window = tk.Toplevel(self.window)
        entry_window.title("New Folder")
        entry_window.transient(self.window)
        entry_window.grab_set()
        entry_window.geometry("420x170")
        entry_window.minsize(360, 150)
        entry_window.configure(bg=self.colors["app_bg"])

        frame = ttk.Frame(entry_window, style="App.TFrame", padding=20)
        frame.pack(fill="both", expand=True)
        ttk.Label(frame, text="Create a folder inside:", style="AppBody.TLabel").pack(anchor="w")
        ttk.Label(frame, text=str(self.current_path), style="Hint.TLabel", wraplength=360, justify="left").pack(anchor="w", pady=(4, 12))
        ttk.Label(frame, text="Folder name", style="AppBody.TLabel").pack(anchor="w")
        entry = ttk.Entry(frame, style="App.TEntry")
        entry.pack(fill="x", pady=(6, 14))

        def create_folder() -> None:
            name = entry.get().strip()
            if not name:
                messagebox.showerror("Folder name required", "Enter a folder name.", parent=entry_window)
                return
            target = self.current_path / name
            try:
                target.mkdir(parents=True, exist_ok=True)
            except OSError as exc:
                messagebox.showerror("Create folder failed", str(exc), parent=entry_window)
                return
            self.current_path = target
            self.refresh_lists()
            entry_window.destroy()

        buttons = ttk.Frame(frame, style="App.TFrame")
        buttons.pack(anchor="e")
        ttk.Button(buttons, text="Cancel", style="Secondary.TButton", command=entry_window.destroy).pack(side="left")
        ttk.Button(buttons, text="Create Folder", style="Primary.TButton", command=create_folder).pack(side="left", padx=(10, 0))

        entry_window.after(50, entry.focus_force)

    def open(self) -> None:
        selected = self.current_path
        if self.folder_list is not None:
            selection = self.folder_list.curselection()
            if selection:
                _, selected, _ = self.folder_details[selection[0]]
        self.result = str(selected)
        self.window.destroy()

    def cancel(self) -> None:
        self.result = ""
        self.window.destroy()

    def show(self) -> str:
        self.window.wait_window()
        return self.result

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
        self.window.geometry("950x520")
        self.window.minsize(860, 440)
        self.window.configure(bg=parent.colors["app_bg"])
        self.window.transient(parent.root)
        self.window.grab_set()

        self.message_queue: queue.Queue[tuple[str, object]] = queue.Queue()
        self.running = False

        self.source_var = tk.StringVar(value=parent.source_var.get() or os.getcwd())
        self.dest_var = tk.StringVar(value=parent.output_dir_var.get() or os.getcwd())
        self.status_var = tk.StringVar(value="Choose a folder to search, then choose where the copied email files should go.")
        self.progress_var = tk.DoubleVar(value=0)
        self.start_button: ttk.Button | None = None
        self.reset_button: ttk.Button | None = None
        self.source_entry: ttk.Entry | None = None
        self.dest_entry: ttk.Entry | None = None
        self.progress: ttk.Progressbar | None = None

        self.build_ui()
        self.window.after(50, self.focus_source_entry)
        self.window.after(100, self.pump_queue)

    def build_ui(self) -> None:
        outer = self.parent.build_scrollable_root(self.window)

        ttk.Label(outer, text="Copy Email Files", style="Title.TLabel").pack(anchor="w")
        ttk.Label(
            outer,
            text="Choose a folder to search, choose where the copied files should go, and the app will save a report of everything that was copied.",
            style="Hint.TLabel",
            wraplength=820,
            justify="left",
        ).pack(anchor="w", pady=(6, 18))

        card = ttk.Frame(outer, style="Card.TFrame", padding=20)
        card.pack(fill="both", expand=True)
        card.columnconfigure(1, weight=1)

        self.source_entry = self.parent.add_path_row(card, 0, "Folder to search", self.source_var, self.choose_source)
        self.dest_entry = self.parent.add_path_row(card, 1, "Copy files into", self.dest_var, self.choose_dest)

        ttk.Label(
            card,
            text="Supported email file types: " + ", ".join(sorted(EMAIL_EXTENSIONS)),
            style="Body.TLabel",
            wraplength=820,
            justify="left",
        ).grid(row=2, column=0, columnspan=3, sticky="w", pady=(12, 14))

        actions = ttk.Frame(card, style="Card.TFrame")
        actions.grid(row=3, column=0, columnspan=3, sticky="w")
        self.start_button = ttk.Button(actions, text="Start Copy", style="Primary.TButton", command=self.start_copy)
        self.start_button.pack(side="left")
        ttk.Button(actions, text="Use Main Output Folder", style="Secondary.TButton", command=self.use_main_output).pack(side="left", padx=(10, 0))
        self.reset_button = ttk.Button(actions, text="Reset", style="Secondary.TButton", command=self.reset_fields)
        self.reset_button.pack(side="left", padx=(10, 0))
        ttk.Button(actions, text="Cancel", style="Secondary.TButton", command=self.window.destroy).pack(side="left", padx=(10, 0))

        self.progress = ttk.Progressbar(card, style="Modern.Horizontal.TProgressbar", variable=self.progress_var, mode="determinate")
        self.progress.grid(row=4, column=0, columnspan=3, sticky="ew", pady=(14, 8))
        ttk.Label(card, textvariable=self.status_var, style="Body.TLabel", wraplength=620, justify="left").grid(
            row=5, column=0, columnspan=3, sticky="w", pady=(4, 0)
        )

    def focus_source_entry(self) -> None:
        if self.source_entry is not None and self.source_entry.winfo_exists():
            self.source_entry.focus_force()
            self.source_entry.icursor("end")

    def choose_source(self) -> None:
        chosen = choose_directory(self.window, "Choose Source Folder", self.source_var.get(), True, self.parent.colors)
        if chosen:
            self.source_var.set(chosen)
            self.status_var.set("Folder selected. Now choose where the copied files should go.")
            if self.dest_entry is not None:
                self.dest_entry.focus_force()
                self.dest_entry.icursor("end")

    def choose_dest(self) -> None:
        chosen = choose_directory(self.window, "Choose Destination Folder", self.dest_var.get(), False, self.parent.colors)
        if chosen:
            self.dest_var.set(chosen)
            self.status_var.set("Destination selected. Click Start Copy when you're ready.")

    def reset_fields(self) -> None:
        self.source_var.set(self.parent.source_var.get() or os.getcwd())
        self.dest_var.set(self.parent.output_dir_var.get() or os.getcwd())
        self.status_var.set("Choose a folder to search, then choose where the copied email files should go.")
        self.progress_var.set(0)
        if self.progress is not None:
            self.progress.configure(maximum=1)
        self.focus_source_entry()

    def use_main_output(self) -> None:
        self.dest_var.set(self.parent.output_dir_var.get() or os.getcwd())
        self.status_var.set("Using the main window results folder as the destination.")

    def start_copy(self) -> None:
        if self.running:
            return

        source = Path(self.source_var.get()).expanduser().resolve()
        dest = Path(self.dest_var.get()).expanduser().resolve()
        if not source.is_dir():
            messagebox.showerror("Invalid source folder", f"Source folder does not exist:\n{source}")
            return

        self.running = True
        self.progress_var.set(0)
        if self.progress is not None:
            self.progress.configure(maximum=1)
        self.status_var.set("Looking for supported email files...")
        if self.start_button is not None:
            self.start_button.configure(state="disabled")
        if self.reset_button is not None:
            self.reset_button.configure(state="disabled")
        thread = threading.Thread(target=self.run_copy_thread, args=(source, dest), daemon=True)
        thread.start()

    def run_copy_thread(self, source: Path, dest: Path) -> None:
        try:
            def on_progress(progress: EmailCopyProgress) -> None:
                self.message_queue.put(("progress", progress))

            result = copy_email_files(source, dest, progress_callback=on_progress)
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
                    if self.reset_button is not None:
                        self.reset_button.configure(state="normal")
                    result: EmailCopyResult = payload
                    self.parent.status_var.set(
                        f"Done. Copied {result.copied} email files to {result.dest_dir}."
                    )
                    self.progress_var.set(self.progress["maximum"])
                    self.parent.append_summary(
                        "\n".join(
                            [
                                "Copy Email Files Complete",
                                f"Searched folder: {result.source_dir}",
                                f"Copied files to: {result.dest_dir}",
                                f"Report saved to: {result.manifest_path}",
                                f"Email files copied: {result.copied}",
                                f"Finished in: {result.elapsed:.2f}s",
                            ]
                        )
                    )
                    messagebox.showinfo(
                        "Done",
                        f"Copied {result.copied} files.\n\nDestination: {result.dest_dir}\nManifest: {result.manifest_path}",
                    )
                    self.window.destroy()
                    return
                if kind == "progress":
                    progress: EmailCopyProgress = payload
                    if progress.phase == "scanning":
                        total = max(1, progress.scanned)
                        if self.progress is not None:
                            self.progress.configure(maximum=total)
                        self.progress_var.set(progress.scanned)
                        self.status_var.set(
                            f"Checking files... Looked at: {progress.scanned}  Matches found: {progress.matched}"
                        )
                    else:
                        total = max(1, progress.total)
                        if self.progress is not None:
                            self.progress.configure(maximum=total)
                        self.progress_var.set(progress.copied)
                        if progress.total == 0:
                            self.status_var.set(
                                f"Finished checking {progress.scanned} files. No supported email files were found."
                            )
                        elif progress.current_relative:
                            self.status_var.set(
                                f"Copying files... {progress.copied} of {progress.total}: {progress.current_relative}"
                            )
                        else:
                            self.status_var.set(
                                f"Found {progress.total} supported email files after checking {progress.scanned} files."
                            )
                if kind == "error":
                    self.running = False
                    if self.start_button is not None:
                        self.start_button.configure(state="normal")
                    if self.reset_button is not None:
                        self.reset_button.configure(state="normal")
                    self.status_var.set("Something went wrong while copying the email files.")
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
        self.theme_mode_var = tk.StringVar(value=load_theme_mode())
        self.colors = palette_for_mode(self.theme_mode_var.get())
        self.root.configure(bg=self.colors["app_bg"])

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
        self.status_var = tk.StringVar(value="Choose a folder to scan, then click Generate Content List.")
        self.progress_var = tk.DoubleVar(value=0)
        self.generate_button: ttk.Button | None = None
        self.email_button: ttk.Button | None = None
        self.about_button: ttk.Button | None = None
        self.open_folder_button: ttk.Button | None = None
        self.reset_button: ttk.Button | None = None
        self.source_entry: ttk.Entry | None = None
        self.output_entry: ttk.Entry | None = None
        self.file_entry: ttk.Entry | None = None
        self.exclude_entry: ttk.Entry | None = None
        self.summary: tk.Text | None = None
        self.root_canvas: tk.Canvas | None = None

        self.configure_style()
        self.build_ui()
        self.root.after(50, self.focus_source_entry)
        self.root.after(100, self.pump_queue)

    def configure_style(self) -> None:
        colors = self.colors
        style = ttk.Style()
        if "clam" in style.theme_names():
            style.theme_use("clam")
        style.configure("App.TFrame", background=colors["app_bg"])
        style.configure("Hero.TFrame", background=colors["hero_bg"])
        style.configure("Card.TFrame", background=colors["card_bg"], relief="flat")
        style.configure("Title.TLabel", background=colors["app_bg"], foreground=colors["title_fg"], font=("Segoe UI", 26, "bold"))
        style.configure("HeroTitle.TLabel", background=colors["hero_bg"], foreground=colors["hero_fg"], font=("Segoe UI", 24, "bold"))
        style.configure("HeroBody.TLabel", background=colors["hero_bg"], foreground=colors["hero_muted"], font=("Segoe UI", 11))
        style.configure("Body.TLabel", background=colors["card_bg"], foreground=colors["body_fg"], font=("Segoe UI", 11))
        style.configure("AppBody.TLabel", background=colors["app_bg"], foreground=colors["body_fg"], font=("Segoe UI", 11))
        style.configure("Hint.TLabel", background=colors["app_bg"], foreground=colors["hint_fg"], font=("Segoe UI", 10))
        style.configure("CardHint.TLabel", background=colors["card_bg"], foreground=colors["hint_fg"], font=("Segoe UI", 10))
        style.configure("Card.TCheckbutton", background=colors["card_bg"], foreground=colors["body_fg"], font=("Segoe UI", 11))
        style.map(
            "Card.TCheckbutton",
            background=[
                ("active", colors["card_bg"]),
                ("selected", colors["card_bg"]),
                ("disabled", colors["card_bg"]),
                ("!disabled", colors["card_bg"]),
            ],
            foreground=[
                ("disabled", colors["hint_fg"]),
                ("!disabled", colors["body_fg"]),
            ],
        )
        style.configure("Hero.TCheckbutton", background=colors["hero_bg"], foreground=colors["hero_fg"], font=("Segoe UI", 10, "bold"))
        style.map(
            "Hero.TCheckbutton",
            background=[
                ("active", colors["hero_bg"]),
                ("selected", colors["hero_bg"]),
                ("disabled", colors["hero_bg"]),
                ("!disabled", colors["hero_bg"]),
            ],
            foreground=[
                ("disabled", colors["hero_muted"]),
                ("!disabled", colors["hero_fg"]),
            ],
        )
        style.configure(
            "Primary.TButton",
            font=("Segoe UI", 11, "bold"),
            background=colors["primary_bg"],
            foreground=colors["primary_fg"],
            bordercolor=colors["primary_bg"],
            focuscolor=colors["primary_bg"],
            lightcolor=colors["primary_bg"],
            darkcolor=colors["primary_bg"],
        )
        style.map(
            "Primary.TButton",
            background=[("active", colors["progress_fill"]), ("disabled", colors["border"])],
            foreground=[("disabled", colors["hero_muted"])],
        )
        style.configure(
            "Secondary.TButton",
            font=("Segoe UI", 10),
            background=colors["secondary_bg"],
            foreground=colors["secondary_fg"],
            bordercolor=colors["border"],
            focuscolor=colors["secondary_bg"],
            lightcolor=colors["secondary_bg"],
            darkcolor=colors["secondary_bg"],
        )
        style.map(
            "Secondary.TButton",
            background=[("active", colors["card_alt_bg"]), ("disabled", colors["border"])],
            foreground=[("disabled", colors["hint_fg"])],
        )
        style.configure(
            "App.TEntry",
            fieldbackground=colors["entry_bg"],
            foreground=colors["entry_fg"],
            insertcolor=colors["entry_fg"],
            bordercolor=colors["border"],
            lightcolor=colors["border"],
            darkcolor=colors["border"],
        )
        style.map(
            "App.TEntry",
            fieldbackground=[("disabled", colors["card_alt_bg"]), ("!disabled", colors["entry_bg"])],
            foreground=[("disabled", colors["hint_fg"]), ("!disabled", colors["entry_fg"])],
        )
        style.configure(
            "Modern.Horizontal.TProgressbar",
            troughcolor=colors["progress_trough"],
            background=colors["progress_fill"],
            bordercolor=colors["progress_trough"],
        )

    def build_ui(self) -> None:
        outer = self.build_scrollable_root(self.root)
        outer.columnconfigure(0, weight=1)
        outer.rowconfigure(1, weight=1)

        hero = ttk.Frame(outer, style="Hero.TFrame", padding=22)
        hero.grid(row=0, column=0, sticky="ew")
        hero.columnconfigure(0, weight=1)
        hero_copy = ttk.Frame(hero, style="Hero.TFrame")
        hero_copy.grid(row=0, column=0, sticky="ew")
        ttk.Label(hero_copy, text="Content List Generator", style="HeroTitle.TLabel").pack(anchor="w")
        ttk.Label(
            hero_copy,
            text=(
                "Create a simple file list from a folder, save an Excel copy if you want one, "
                "or copy supported email files into a new folder with a saved report."
            ),
            style="HeroBody.TLabel",
            wraplength=820,
            justify="left",
        ).pack(anchor="w", pady=(8, 0))
        appearance = ttk.Frame(hero, style="Hero.TFrame")
        appearance.grid(row=0, column=1, sticky="ne")
        ttk.Label(appearance, text="Appearance", style="HeroBody.TLabel").pack(anchor="e")
        ttk.Checkbutton(
            appearance,
            text="Dark mode",
            variable=self.theme_mode_var,
            onvalue="dark",
            offvalue="light",
            style="Hero.TCheckbutton",
            command=self.toggle_theme,
        ).pack(anchor="e", pady=(8, 0))

        main_card = ttk.Frame(outer, style="Card.TFrame", padding=22)
        main_card.grid(row=1, column=0, sticky="nsew", pady=(18, 0))
        main_card.columnconfigure(1, weight=1)
        main_card.rowconfigure(8, weight=1)

        ttk.Label(main_card, text="Create a Content List", style="Body.TLabel").grid(row=0, column=0, sticky="w")
        ttk.Label(
            main_card,
            text="Choose a folder, choose where to save the results, and click Generate Content List.",
            style="CardHint.TLabel",
        ).grid(row=1, column=0, columnspan=3, sticky="w", pady=(4, 14))

        self.source_entry = self.add_path_row(main_card, 2, "Folder to scan", self.source_var, self.choose_source)
        self.output_entry = self.add_path_row(main_card, 3, "Save results to", self.output_dir_var, self.choose_output)
        self.file_entry = self.add_entry_row(main_card, 4, "Name for the saved list", self.output_name_var)
        self.exclude_entry = self.add_entry_row(main_card, 5, "Skip file types (optional)", self.exclude_var, "Example: tmp,log,bak")

        options = ttk.Frame(main_card, style="Card.TFrame")
        options.grid(row=6, column=0, columnspan=3, sticky="ew", pady=(14, 6))
        ttk.Checkbutton(options, text="Add SHA-256 hashes (advanced)", variable=self.hash_var, style="Card.TCheckbutton").pack(anchor="w")
        ttk.Checkbutton(options, text="Skip hidden files", variable=self.hidden_var, style="Card.TCheckbutton").pack(anchor="w")
        ttk.Checkbutton(options, text="Skip common system files", variable=self.system_var, style="Card.TCheckbutton").pack(anchor="w")
        ttk.Checkbutton(options, text="Also save an Excel copy", variable=self.xlsx_var, command=self.sync_xlsx_state, style="Card.TCheckbutton").pack(anchor="w")
        self.preserve_zeros_toggle = ttk.Checkbutton(
            options,
            text="Keep leading zeros in Excel",
            variable=self.preserve_zeros_var,
            style="Card.TCheckbutton",
        )
        self.preserve_zeros_toggle.pack(anchor="w")

        actions = ttk.Frame(main_card, style="Card.TFrame")
        actions.grid(row=7, column=0, columnspan=3, sticky="ew", pady=(16, 10))
        self.generate_button = ttk.Button(actions, text="Generate Content List", style="Primary.TButton", command=self.start_scan)
        self.generate_button.pack(side="left")
        self.email_button = ttk.Button(actions, text="Copy Email Files", style="Secondary.TButton", command=self.open_email_copy_window)
        self.email_button.pack(side="left", padx=(10, 0))
        ttk.Button(actions, text="Use Source As Output", style="Secondary.TButton", command=self.copy_source_to_output).pack(side="left", padx=(10, 0))
        self.reset_button = ttk.Button(actions, text="Reset", style="Secondary.TButton", command=self.reset_fields)
        self.reset_button.pack(side="left", padx=(10, 0))
        self.about_button = ttk.Button(actions, text="About", style="Secondary.TButton", command=self.show_about_dialog)
        self.about_button.pack(side="left", padx=(10, 0))
        self.open_folder_button = ttk.Button(actions, text="Open Output Folder", style="Secondary.TButton", command=self.open_output_folder)
        self.open_folder_button.pack(side="left", padx=(10, 0))

        self.progress = ttk.Progressbar(main_card, style="Modern.Horizontal.TProgressbar", variable=self.progress_var, mode="determinate")
        self.progress.grid(row=8, column=0, columnspan=3, sticky="ew", pady=(0, 8))
        ttk.Label(main_card, textvariable=self.status_var, style="Body.TLabel").grid(row=9, column=0, columnspan=3, sticky="w")

        ttk.Label(main_card, text="Summary", style="Body.TLabel").grid(row=10, column=0, sticky="w", pady=(18, 8))
        self.summary = tk.Text(
            main_card,
            height=16,
            wrap="word",
            bd=0,
            bg=self.colors["card_alt_bg"],
            fg=self.colors["body_fg"],
            insertbackground=self.colors["body_fg"],
            font=("Consolas", 11),
        )
        self.summary.grid(row=11, column=0, columnspan=3, sticky="nsew")
        main_card.rowconfigure(11, weight=1)

        self.sync_xlsx_state()
        self.sync_action_buttons()

    def build_scrollable_root(self, parent) -> ttk.Frame:
        shell = ttk.Frame(parent, style="App.TFrame")
        shell.pack(fill="both", expand=True)
        shell.columnconfigure(0, weight=1)
        shell.rowconfigure(0, weight=1)

        canvas = tk.Canvas(shell, background=self.colors["app_bg"], highlightthickness=0, bd=0)
        scrollbar = ttk.Scrollbar(shell, orient="vertical", command=canvas.yview)
        canvas.configure(yscrollcommand=scrollbar.set)
        if parent is self.root:
            self.root_canvas = canvas

        canvas.grid(row=0, column=0, sticky="nsew")
        scrollbar.grid(row=0, column=1, sticky="ns")

        inner = ttk.Frame(canvas, style="App.TFrame", padding=24)
        window_id = canvas.create_window((0, 0), window=inner, anchor="nw")

        def sync_scroll_region(_event=None) -> None:
            canvas.configure(scrollregion=canvas.bbox("all"))

        def fit_inner_width(event) -> None:
            canvas.itemconfigure(window_id, width=event.width)

        inner.bind("<Configure>", sync_scroll_region)
        canvas.bind("<Configure>", fit_inner_width)

        def on_mousewheel(event) -> None:
            if event.delta:
                canvas.yview_scroll(int(-event.delta / 120), "units")

        def bind_mousewheel(_event=None) -> None:
            canvas.bind_all("<MouseWheel>", on_mousewheel)

        def unbind_mousewheel(_event=None) -> None:
            canvas.unbind_all("<MouseWheel>")

        canvas.bind("<Enter>", bind_mousewheel)
        canvas.bind("<Leave>", unbind_mousewheel)

        return inner

    def focus_source_entry(self) -> None:
        if self.source_entry is not None and self.source_entry.winfo_exists():
            self.source_entry.focus_force()
            self.source_entry.icursor("end")

    def add_path_row(self, parent, row: int, label: str, variable: tk.StringVar, command) -> ttk.Entry:
        ttk.Label(parent, text=label, style="Body.TLabel").grid(row=row, column=0, sticky="w", pady=6, padx=(0, 12))
        entry = ttk.Entry(parent, textvariable=variable, style="App.TEntry")
        entry.grid(row=row, column=1, sticky="ew", pady=6)
        ttk.Button(parent, text="Browse", style="Secondary.TButton", command=command).grid(row=row, column=2, padx=(12, 0), pady=6)
        return entry

    def add_entry_row(self, parent, row: int, label: str, variable: tk.StringVar, hint: str = "") -> ttk.Entry:
        ttk.Label(parent, text=label, style="Body.TLabel").grid(row=row, column=0, sticky="w", pady=6, padx=(0, 12))
        entry = ttk.Entry(parent, textvariable=variable, style="App.TEntry")
        entry.grid(row=row, column=1, columnspan=2, sticky="ew", pady=6)
        if hint:
            ttk.Label(parent, text=hint, style="Hint.TLabel").grid(row=row + 1, column=1, columnspan=2, sticky="w")
        return entry

    def toggle_theme(self) -> None:
        self.colors = palette_for_mode(self.theme_mode_var.get())
        save_theme_mode(self.theme_mode_var.get())
        self.root.configure(bg=self.colors["app_bg"])
        self.configure_style()
        if self.root_canvas is not None and self.root_canvas.winfo_exists():
            self.root_canvas.configure(background=self.colors["app_bg"])
        if self.summary is not None and self.summary.winfo_exists():
            self.summary.configure(
                bg=self.colors["card_alt_bg"],
                fg=self.colors["body_fg"],
                insertbackground=self.colors["body_fg"],
            )

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
        if self.reset_button is not None:
            self.reset_button.configure(state=running_state)
        if self.about_button is not None:
            self.about_button.configure(state="normal")

    def choose_source(self) -> None:
        chosen = choose_directory(self.root, "Choose Source Folder", self.source_var.get(), True, self.colors)
        if chosen:
            self.source_var.set(chosen)
            if not self.output_name_var.get().strip():
                self.output_name_var.set(default_output_name(Path(chosen)))

    def choose_output(self) -> None:
        chosen = choose_directory(self.root, "Choose Output Folder", self.output_dir_var.get(), False, self.colors)
        if chosen:
            self.output_dir_var.set(chosen)

    def copy_source_to_output(self) -> None:
        self.output_dir_var.set(self.source_var.get())

    def reset_fields(self) -> None:
        cwd = Path(os.getcwd())
        self.source_var.set(str(cwd))
        self.output_dir_var.set(str(cwd))
        self.output_name_var.set(default_output_name(cwd))
        self.exclude_var.set("")
        self.hash_var.set(False)
        self.hidden_var.set(False)
        self.system_var.set(False)
        self.xlsx_var.set(False)
        self.preserve_zeros_var.set(False)
        self.progress_var.set(0)
        self.status_var.set("Choose a folder to scan, then click Generate Content List.")
        self.append_summary("")
        if self.progress is not None:
            self.progress.configure(maximum=1)
        self.sync_xlsx_state()
        self.focus_source_entry()

    def show_about_dialog(self) -> None:
        window = tk.Toplevel(self.root)
        window.title("About Content List Generator")
        window.geometry("640x360")
        window.minsize(560, 320)
        window.configure(bg=self.colors["app_bg"])
        window.transient(self.root)
        window.grab_set()

        card = ttk.Frame(window, style="App.TFrame", padding=24)
        card.pack(fill="both", expand=True)

        ttk.Label(card, text="About Content List Generator", style="Title.TLabel").pack(anchor="w")
        ttk.Label(
            card,
            text=(
                "Content List Generator helps you create a simple file list from a folder "
                "and copy supported email files into a new location."
            ),
            style="Hint.TLabel",
            wraplength=560,
            justify="left",
        ).pack(anchor="w", pady=(8, 16))
        ttk.Label(card, text="Written by Bryan Snyder", style="AppBody.TLabel").pack(anchor="w")
        ttk.Label(card, text="GitHub: placeholder link", style="AppBody.TLabel").pack(anchor="w", pady=(10, 0))
        ttk.Button(card, text="Open GitHub Link", style="Secondary.TButton", command=lambda: webbrowser.open_new_tab(PLACEHOLDER_GITHUB_URL)).pack(anchor="w", pady=(8, 16))
        ttk.Label(
            card,
            text=(
                "Open source note:\n"
                "- This project is being prepared for an open source release.\n"
                "- TODO: decide the final attribution requirement before publishing."
            ),
            style="AppBody.TLabel",
            justify="left",
        ).pack(anchor="w")
        ttk.Button(card, text="Close", style="Primary.TButton", command=window.destroy).pack(anchor="e", pady=(20, 0))

    def open_email_copy_window(self) -> None:
        if self.running:
            return
        EmailCopyWindow(self)

    def open_output_folder(self) -> None:
        open_in_file_manager(Path(self.output_dir_var.get() or os.getcwd()))

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
        self.status_var.set("Getting everything ready...")
        self.append_summary("Preparing your file list...")

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
            self.message_queue.put(("status", f"Saving {len(files)} files into the list..."))

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
                    self.status_var.set(f"Working... {current} of {total}: {name}")
                elif kind == "done":
                    self.running = False
                    result = payload
                    self.status_var.set(f"Your file list is ready. {result.files} files were included.")
                    self.append_summary(build_scan_summary(result))
                    self.progress_var.set(self.progress["maximum"])
                    self.sync_action_buttons()
                elif kind == "error":
                    self.running = False
                    self.status_var.set("Something went wrong while making the file list.")
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
