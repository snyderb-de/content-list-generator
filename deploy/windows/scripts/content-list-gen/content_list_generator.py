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

try:
    import customtkinter as ctk
except Exception:  # pragma: no cover
    ctk = None

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
            "app_bg": "#0c131b",
            "sidebar_bg": "#101923",
            "hero_bg": "#0c1722",
            "hero_card_bg": "#122130",
            "card_bg": "#13202b",
            "card_alt_bg": "#182633",
            "title_fg": "#edf4fb",
            "hero_fg": "#f5f9fd",
            "hero_muted": "#bfd0df",
            "body_fg": "#ebf1f7",
            "hint_fg": "#9caebf",
            "entry_bg": "#0f1822",
            "entry_fg": "#edf4fb",
            "border": "#263749",
            "progress_trough": "#243443",
            "progress_fill": "#5e9fff",
            "primary_bg": "#4d8ef8",
            "primary_hover": "#69a2ff",
            "primary_fg": "#f8fbff",
            "secondary_bg": "#1b2a38",
            "secondary_hover": "#213447",
            "secondary_fg": "#edf4fb",
            "selection_bg": "#204a73",
            "selection_fg": "#f8fbff",
            "sidebar_active_bg": "#173455",
            "sidebar_active_fg": "#f6fbff",
            "sidebar_idle_fg": "#b4c4d3",
            "chip_bg": "#0f1822",
            "success_fg": "#9fd2a2",
        }
    return {
        "app_bg": "#ebf1f5",
        "sidebar_bg": "#f2f4f6",
        "hero_bg": "#13324a",
        "hero_card_bg": "#f7fafc",
        "card_bg": "#ffffff",
        "card_alt_bg": "#f3f6f9",
        "title_fg": "#14324a",
        "hero_fg": "#ffffff",
        "hero_muted": "#dce8f3",
        "body_fg": "#243849",
        "hint_fg": "#556778",
        "entry_bg": "#ffffff",
        "entry_fg": "#243746",
        "border": "#cad6e0",
        "progress_trough": "#d7e1ea",
        "progress_fill": "#005bc1",
        "primary_bg": "#005bc1",
        "primary_hover": "#0070eb",
        "primary_fg": "#ffffff",
        "secondary_bg": "#eef3f7",
        "secondary_hover": "#e1e8ef",
        "secondary_fg": "#32485a",
        "selection_bg": "#d7e7ff",
        "selection_fg": "#12324a",
        "sidebar_active_bg": "#d6e6ff",
        "sidebar_active_fg": "#0f4c98",
        "sidebar_idle_fg": "#526276",
        "chip_bg": "#eef3f7",
        "success_fg": "#2d7c48",
    }


LIGHT_PALETTE = palette_for_mode("light")
DARK_PALETTE = palette_for_mode("dark")


def themed_color(key: str) -> tuple[str, str]:
    return (LIGHT_PALETTE[key], DARK_PALETTE[key])


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

    hashing = args.hashing or prompt_yes_no("Include SHA-256 hashes?", default=True)
    include_hidden = args.include_hidden or prompt_yes_no("Include hidden files?", default=False)
    include_system = args.include_system or prompt_yes_no("Include common system files?", default=False)
    exclude_raw = args.exclude_exts or prompt("Exclude extensions (comma-separated)", "")
    excluded_exts = normalize_exts(exclude_raw)
    create_xlsx = args.create_xlsx or prompt_yes_no("Create XLSX after the CSV scan?", default=True)
    preserve_zeros = False
    if create_xlsx:
        preserve_zeros = args.preserve_zeros or prompt_yes_no("Preserve leading zeros in XLSX?", default=True)

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


class EmailCopyPage:
    def __init__(self, parent: "ContentListApp", host) -> None:
        self.parent = parent
        self.page = parent.build_scrollable_root(host)
        self.page.pack_forget()

        self.message_queue: queue.Queue[tuple[str, object]] = queue.Queue()
        self.running = False
        self.latest_manifest = ""

        self.source_var = tk.StringVar(value=parent.source_var.get() or os.getcwd())
        self.dest_var = tk.StringVar(value=parent.output_dir_var.get() or os.getcwd())
        self.status_var = tk.StringVar(value="Choose a folder to search, then choose where the copied email files should go.")
        self.detail_var = tk.StringVar(value="The app will first look for supported email file types, then copy the matches and save a report.")
        self.phase_var = tk.StringVar(value="Idle")
        self.percent_var = tk.StringVar(value="0%")
        self.scanned_var = tk.StringVar(value="0")
        self.matched_var = tk.StringVar(value="0")
        self.copied_var = tk.StringVar(value="0")
        self.start_button: ctk.CTkButton | None = None
        self.reset_button: ctk.CTkButton | None = None
        self.source_entry: ctk.CTkEntry | None = None
        self.dest_entry: ctk.CTkEntry | None = None
        self.progress: ctk.CTkProgressBar | None = None
        self.summary_box: ctk.CTkTextbox | None = None
        self.manifest_button: ctk.CTkButton | None = None

        self.build_ui()
        self.page.after(100, self.pump_queue)

    def build_ui(self) -> None:
        outer = self.page
        outer.grid_columnconfigure(0, weight=1)
        outer.grid_columnconfigure(1, weight=1)

        hero = ctk.CTkFrame(outer, fg_color=themed_color("hero_card_bg"), corner_radius=22)
        hero.grid(row=0, column=0, columnspan=2, sticky="ew", padx=28, pady=(28, 0))
        hero.grid_columnconfigure(0, weight=1)
        ctk.CTkLabel(
            hero,
            text="Copy Email Files",
            font=ctk.CTkFont(size=30, weight="bold"),
            text_color=themed_color("title_fg"),
        ).grid(row=0, column=0, sticky="w", padx=28, pady=(24, 0))
        ctk.CTkLabel(
            hero,
            text="Choose a folder to search, choose where the copied files should go, and the app will save a report of everything that was copied.",
            text_color=themed_color("hint_fg"),
            font=ctk.CTkFont(size=14),
            wraplength=760,
            justify="left",
        ).grid(row=1, column=0, sticky="w", padx=28, pady=(8, 24))

        hero_status = ctk.CTkFrame(hero, fg_color=themed_color("card_bg"), corner_radius=18)
        hero_status.grid(row=0, column=1, rowspan=2, sticky="ne", padx=24, pady=24)
        ctk.CTkLabel(hero_status, textvariable=self.phase_var, font=ctk.CTkFont(size=12, weight="bold"), text_color=themed_color("hint_fg")).pack(anchor="e", padx=18, pady=(14, 0))
        ctk.CTkLabel(hero_status, textvariable=self.percent_var, font=ctk.CTkFont(size=28, weight="bold"), text_color=themed_color("body_fg")).pack(anchor="e", padx=18, pady=(4, 14))

        input_card = ctk.CTkFrame(outer, fg_color=themed_color("card_bg"), corner_radius=22)
        input_card.grid(row=1, column=0, sticky="nsew", padx=(28, 10), pady=(18, 0))
        input_card.grid_columnconfigure(0, weight=1)

        ctk.CTkLabel(input_card, text="Folders", font=ctk.CTkFont(size=20, weight="bold"), text_color=themed_color("body_fg")).grid(row=0, column=0, sticky="w", padx=24, pady=(22, 4))
        ctk.CTkLabel(
            input_card,
            text="The copied files keep the same folder structure they had in the folder you search.",
            font=ctk.CTkFont(size=13),
            text_color=themed_color("hint_fg"),
            wraplength=660,
            justify="left",
        ).grid(row=1, column=0, sticky="w", padx=24, pady=(0, 16))

        source_card = self.parent.make_field_card(input_card, "Folder to search", self.source_var, self.choose_source)
        source_card.grid(row=2, column=0, padx=24, pady=(0, 14), sticky="ew")
        self.source_entry = source_card.entry
        dest_card = self.parent.make_field_card(input_card, "Copy files into", self.dest_var, self.choose_dest)
        dest_card.grid(row=3, column=0, padx=24, pady=(0, 18), sticky="ew")
        self.dest_entry = dest_card.entry

        actions = ctk.CTkFrame(input_card, fg_color="transparent")
        actions.grid(row=4, column=0, sticky="ew", padx=24, pady=(0, 22))
        self.start_button = self.parent.make_primary_button(actions, "Copy Email Files", self.start_copy)
        self.start_button.pack(side="left")
        self.parent.make_secondary_button(actions, "Use Main Output Folder", self.use_main_output).pack(side="left", padx=(10, 0))
        self.reset_button = self.parent.make_secondary_button(actions, "Reset", self.reset_fields)
        self.reset_button.pack(side="left", padx=(10, 0))
        self.parent.make_secondary_button(actions, "Back to Content List", lambda: self.parent.show_page("content")).pack(side="left", padx=(10, 0))

        side_card = ctk.CTkFrame(outer, fg_color=themed_color("card_bg"), corner_radius=22)
        side_card.grid(row=1, column=1, sticky="nsew", padx=(10, 28), pady=(18, 0))
        side_card.grid_columnconfigure(0, weight=1)

        ctk.CTkLabel(side_card, text="Supported email file types", font=ctk.CTkFont(size=20, weight="bold"), text_color=themed_color("body_fg")).grid(row=0, column=0, sticky="w", padx=24, pady=(22, 6))
        chip_box = ctk.CTkFrame(side_card, fg_color=themed_color("chip_bg"), corner_radius=18)
        chip_box.grid(row=1, column=0, sticky="ew", padx=24)
        chip_text = "\n".join(sorted(EMAIL_EXTENSIONS))
        ctk.CTkLabel(
            chip_box,
            text=chip_text,
            font=ctk.CTkFont(size=13, family="Menlo"),
            text_color=themed_color("body_fg"),
            justify="left",
        ).pack(anchor="w", padx=18, pady=16)
        ctk.CTkLabel(
            side_card,
            text="The app checks folders for these file types first, then copies the matches and writes a report.",
            text_color=themed_color("hint_fg"),
            font=ctk.CTkFont(size=12),
            wraplength=260,
            justify="left",
        ).grid(row=2, column=0, sticky="w", padx=24, pady=(14, 18))

        stats = ctk.CTkFrame(side_card, fg_color="transparent")
        stats.grid(row=3, column=0, sticky="ew", padx=24, pady=(0, 22))
        stats.grid_columnconfigure((0, 1, 2), weight=1)
        self.parent.make_metric_card(stats, "Files Checked", self.scanned_var).grid(row=0, column=0, sticky="ew", padx=(0, 8))
        self.parent.make_metric_card(stats, "Matches Found", self.matched_var, accent=True).grid(row=0, column=1, sticky="ew", padx=4)
        self.parent.make_metric_card(stats, "Files Copied", self.copied_var, accent=True).grid(row=0, column=2, sticky="ew", padx=(8, 0))

        progress_card = ctk.CTkFrame(outer, fg_color=themed_color("card_bg"), corner_radius=22)
        progress_card.grid(row=2, column=0, columnspan=2, sticky="ew", padx=28, pady=(18, 0))
        progress_card.grid_columnconfigure(0, weight=1)
        ctk.CTkLabel(progress_card, text="Progress", font=ctk.CTkFont(size=18, weight="bold"), text_color=themed_color("body_fg")).grid(row=0, column=0, sticky="w", padx=24, pady=(20, 8))
        self.progress = ctk.CTkProgressBar(progress_card, progress_color=themed_color("progress_fill"), mode="determinate")
        self.progress.grid(row=1, column=0, sticky="ew", padx=24)
        self.progress.set(0)
        ctk.CTkLabel(progress_card, textvariable=self.status_var, text_color=themed_color("body_fg"), wraplength=980, justify="left").grid(row=2, column=0, sticky="w", padx=24, pady=(12, 0))
        ctk.CTkLabel(progress_card, textvariable=self.detail_var, text_color=themed_color("hint_fg"), wraplength=980, justify="left").grid(row=3, column=0, sticky="w", padx=24, pady=(6, 18))

        summary_card = ctk.CTkFrame(outer, fg_color=themed_color("card_bg"), corner_radius=22)
        summary_card.grid(row=3, column=0, columnspan=2, sticky="nsew", padx=28, pady=(18, 28))
        summary_card.grid_columnconfigure(0, weight=1)
        ctk.CTkLabel(summary_card, text="Copy Summary", font=ctk.CTkFont(size=18, weight="bold"), text_color=themed_color("body_fg")).grid(row=0, column=0, sticky="w", padx=24, pady=(20, 8))
        self.summary_box = ctk.CTkTextbox(
            summary_card,
            height=180,
            wrap="word",
            fg_color=themed_color("card_alt_bg"),
            text_color=themed_color("body_fg"),
            border_width=0,
            font=("Menlo", 11),
        )
        self.summary_box.grid(row=1, column=0, sticky="nsew", padx=24, pady=(0, 18))
        self.summary_box.insert("1.0", "Your copy summary will appear here after the job is finished.")
        self.summary_box.configure(state="disabled")

        footer_actions = ctk.CTkFrame(summary_card, fg_color="transparent")
        footer_actions.grid(row=2, column=0, sticky="e", padx=24, pady=(0, 20))
        self.manifest_button = self.parent.make_secondary_button(footer_actions, "Open Manifest", self.open_manifest)
        self.manifest_button.pack(side="left")
        self.manifest_button.configure(state="disabled")
        self.parent.make_secondary_button(footer_actions, "Open Destination", self.open_destination).pack(side="left", padx=(10, 0))

    def focus_source_entry(self) -> None:
        if self.source_entry is not None and self.source_entry.winfo_exists():
            self.source_entry.focus_force()
            self.source_entry.icursor("end")

    def choose_source(self) -> None:
        chosen = choose_directory(self.parent.root, "Choose Source Folder", self.source_var.get(), True, self.parent.colors)
        if chosen:
            self.source_var.set(chosen)
            self.status_var.set("Folder selected. Now choose where the copied files should go.")
            if self.dest_entry is not None:
                self.dest_entry.focus_force()
                self.dest_entry.icursor("end")

    def choose_dest(self) -> None:
        chosen = choose_directory(self.parent.root, "Choose Destination Folder", self.dest_var.get(), False, self.parent.colors)
        if chosen:
            self.dest_var.set(chosen)
            self.status_var.set("Destination selected. Click Start Copy when you're ready.")

    def reset_fields(self) -> None:
        self.source_var.set(self.parent.source_var.get() or os.getcwd())
        self.dest_var.set(self.parent.output_dir_var.get() or os.getcwd())
        self.status_var.set("Choose a folder to search, then choose where the copied email files should go.")
        self.detail_var.set("The app will first look for supported email file types, then copy the matches and save a report.")
        self.phase_var.set("Idle")
        self.percent_var.set("0%")
        self.scanned_var.set("0")
        self.matched_var.set("0")
        self.copied_var.set("0")
        self.latest_manifest = ""
        if self.progress is not None:
            self.set_progress_mode("determinate")
            self.progress.set(0)
        if self.manifest_button is not None:
            self.manifest_button.configure(state="disabled")
        self.set_summary("Your copy summary will appear here after the job is finished.")
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
        if self.progress is not None:
            self.set_progress_mode("indeterminate")
            self.progress.set(0)
            self.progress.start()
        self.phase_var.set("Scanning")
        self.percent_var.set("Scanning")
        self.status_var.set("Looking for supported email files...")
        self.detail_var.set("Checking folders for supported email file types before the copy begins.")
        self.scanned_var.set("0")
        self.matched_var.set("0")
        self.copied_var.set("0")
        self.set_summary("Preparing the copy job...")
        if self.start_button is not None:
            self.start_button.configure(state="disabled")
        if self.reset_button is not None:
            self.reset_button.configure(state="disabled")
        if self.manifest_button is not None:
            self.manifest_button.configure(state="disabled")
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
                    self.latest_manifest = str(result.manifest_path)
                    self.phase_var.set("Complete")
                    self.percent_var.set("100%")
                    self.parent.status_var.set(
                        f"Done. Copied {result.copied} email files to {result.dest_dir}."
                    )
                    if self.progress is not None:
                        self.progress.stop()
                        self.set_progress_mode("determinate")
                        self.progress.set(1)
                    if self.manifest_button is not None:
                        self.manifest_button.configure(state="normal")
                    self.set_summary(
                        "\n".join(
                            [
                                "Copy Email Files Complete",
                                f"Searched folder: {result.source_dir}",
                                f"Copied files to: {result.dest_dir}",
                                f"Report saved to: {result.manifest_path}",
                                f"Email files copied: {result.copied}",
                                f"Finished in: {result.elapsed:.2f}s",
                                "",
                                "Supported email file types:",
                                ", ".join(sorted(EMAIL_EXTENSIONS)),
                            ]
                        )
                    )
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
                    self.detail_var.set("The report was saved and the original folder structure was preserved.")
                    messagebox.showinfo(
                        "Done",
                        f"Copied {result.copied} files.\n\nDestination: {result.dest_dir}\nManifest: {result.manifest_path}",
                    )
                if kind == "progress":
                    progress: EmailCopyProgress = payload
                    self.scanned_var.set(str(progress.scanned))
                    self.matched_var.set(str(progress.matched))
                    if progress.phase == "scanning":
                        self.phase_var.set("Scanning")
                        self.percent_var.set("Scanning")
                        self.status_var.set(
                            f"Checking files... Looked at: {progress.scanned}  Matches found: {progress.matched}"
                        )
                        if progress.current_name:
                            self.detail_var.set(f"Checking: {progress.current_name}")
                        else:
                            self.detail_var.set("Checking folders for supported email file types.")
                    else:
                        self.phase_var.set("Copying")
                        total = max(1, progress.total)
                        if self.progress is not None:
                            self.progress.stop()
                            self.set_progress_mode("determinate")
                            self.progress.set(progress.copied / total)
                        self.percent_var.set(f"{int((progress.copied / total) * 100)}%")
                        self.copied_var.set(str(progress.copied))
                        if progress.total == 0:
                            self.status_var.set(
                                f"Finished checking {progress.scanned} files. No supported email files were found."
                            )
                            self.detail_var.set("Nothing matched the supported email file types in this folder.")
                        elif progress.current_relative:
                            self.status_var.set(
                                f"Copying files... {progress.copied} of {progress.total}: {progress.current_relative}"
                            )
                            self.detail_var.set(
                                f"Found {progress.total} supported email files after checking {progress.scanned} files."
                            )
                        else:
                            self.status_var.set(
                                f"Found {progress.total} supported email files after checking {progress.scanned} files."
                            )
                            self.detail_var.set("Starting the copy now.")
                if kind == "error":
                    self.running = False
                    if self.start_button is not None:
                        self.start_button.configure(state="normal")
                    if self.reset_button is not None:
                        self.reset_button.configure(state="normal")
                    if self.progress is not None:
                        self.progress.stop()
                        self.set_progress_mode("determinate")
                    self.status_var.set("Something went wrong while copying the email files.")
                    self.phase_var.set("Error")
                    self.percent_var.set("0%")
                    messagebox.showerror("Copy failed", str(payload))
        except queue.Empty:
            pass
        if self.page.winfo_exists():
            self.page.after(100, self.pump_queue)

    def set_progress_mode(self, mode: str) -> None:
        if self.progress is None:
            return
        self.progress.configure(mode=mode)

    def set_summary(self, text: str) -> None:
        if self.summary_box is None:
            return
        self.summary_box.configure(state="normal")
        self.summary_box.delete("1.0", "end")
        self.summary_box.insert("end", text)
        self.summary_box.configure(state="disabled")

    def open_manifest(self) -> None:
        if self.latest_manifest:
            open_in_file_manager(Path(self.latest_manifest))

    def open_destination(self) -> None:
        open_in_file_manager(Path(self.dest_var.get() or os.getcwd()))


class ContentListApp:
    def __init__(self) -> None:
        ctk.set_default_color_theme("blue")
        ctk.set_appearance_mode(load_theme_mode())
        self.root = ctk.CTk()
        self.root.title("Content List Generator")
        self.root.geometry("1360x860")
        self.root.minsize(1160, 760)
        self.theme_mode_var = tk.StringVar(value=load_theme_mode())
        self.colors = palette_for_mode(self.theme_mode_var.get())
        self.root.configure(fg_color=themed_color("app_bg"))

        self.message_queue: queue.Queue[tuple[str, object]] = queue.Queue()
        self.running = False
        self.active_page = "content"

        cwd = Path(os.getcwd())
        self.source_var = tk.StringVar(value=str(cwd))
        self.output_dir_var = tk.StringVar(value=str(cwd))
        self.output_name_var = tk.StringVar(value=default_output_name(cwd))
        self.exclude_var = tk.StringVar(value="")
        self.hash_var = tk.BooleanVar(value=True)
        self.hidden_var = tk.BooleanVar(value=False)
        self.system_var = tk.BooleanVar(value=False)
        self.xlsx_var = tk.BooleanVar(value=True)
        self.preserve_zeros_var = tk.BooleanVar(value=True)
        self.status_var = tk.StringVar(value="Choose a folder to scan, then click Generate Content List.")
        self.scan_files_var = tk.StringVar(value="0")
        self.scan_skipped_var = tk.StringVar(value="0")
        self.scan_saved_var = tk.StringVar(value="Waiting")
        self.generate_button: ctk.CTkButton | None = None
        self.email_button: ctk.CTkButton | None = None
        self.about_button: ctk.CTkButton | None = None
        self.open_folder_button: ctk.CTkButton | None = None
        self.reset_button: ctk.CTkButton | None = None
        self.source_entry: ctk.CTkEntry | None = None
        self.output_entry: ctk.CTkEntry | None = None
        self.file_entry: ctk.CTkEntry | None = None
        self.exclude_entry: ctk.CTkEntry | None = None
        self.summary: ctk.CTkTextbox | None = None
        self.progress: ctk.CTkProgressBar | None = None
        self.preserve_zeros_toggle: ctk.CTkCheckBox | None = None
        self.page_frames: dict[str, ctk.CTkFrame] = {}
        self.nav_buttons: dict[str, ctk.CTkButton] = {}
        self.email_page = None

        self.configure_style()
        self.build_ui()
        self.bind_app_scrolling()
        self.root.after(50, self.focus_source_entry)
        self.root.after(100, self.pump_queue)

    def configure_style(self) -> None:
        colors = self.colors
        style = ttk.Style()
        if "clam" in style.theme_names():
            style.theme_use("clam")
        style.configure("App.TFrame", background=colors["app_bg"])
        style.configure("Card.TFrame", background=colors["card_bg"], relief="flat")
        style.configure("Panel.TFrame", background=colors["card_alt_bg"], relief="flat")
        style.configure("Title.TLabel", background=colors["app_bg"], foreground=colors["title_fg"], font=("Segoe UI", 26, "bold"))
        style.configure("Body.TLabel", background=colors["card_bg"], foreground=colors["body_fg"], font=("Segoe UI", 11))
        style.configure("AppBody.TLabel", background=colors["app_bg"], foreground=colors["body_fg"], font=("Segoe UI", 11))
        style.configure("Hint.TLabel", background=colors["app_bg"], foreground=colors["hint_fg"], font=("Segoe UI", 10))
        style.configure("CardHint.TLabel", background=colors["card_bg"], foreground=colors["hint_fg"], font=("Segoe UI", 10))
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
            background=[("active", colors["primary_hover"]), ("disabled", colors["border"])],
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
            background=[("active", colors["secondary_hover"]), ("disabled", colors["border"])],
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
        shell = ctk.CTkFrame(self.root, fg_color=themed_color("app_bg"), corner_radius=0)
        shell.pack(fill="both", expand=True)

        sidebar = ctk.CTkFrame(shell, width=304, fg_color=themed_color("sidebar_bg"), corner_radius=18)
        sidebar.pack(side="left", fill="y", padx=(18, 10), pady=18)
        sidebar.pack_propagate(False)

        content_shell = ctk.CTkFrame(shell, fg_color=themed_color("app_bg"), corner_radius=0)
        content_shell.pack(side="left", fill="both", expand=True, padx=(10, 18), pady=18)

        self.build_sidebar(sidebar)
        self.page_frames["content"] = self.build_content_page(content_shell)
        self.page_frames["email"] = self.build_email_page(content_shell)
        self.page_frames["about"] = self.build_about_page(content_shell)
        self.show_page("content")
        self.sync_xlsx_state()
        self.sync_action_buttons()

    def build_scrollable_root(self, parent) -> ctk.CTkScrollableFrame:
        shell = ctk.CTkScrollableFrame(parent, fg_color=themed_color("app_bg"), corner_radius=0)
        shell.pack(fill="both", expand=True, padx=0, pady=0)
        return shell

    def bind_app_scrolling(self) -> None:
        self.root.bind_all("<MouseWheel>", self.on_mousewheel, add="+")
        self.root.bind_all("<Shift-MouseWheel>", self.on_shift_mousewheel, add="+")
        self.root.bind_all("<Button-4>", self.on_linux_scroll_up, add="+")
        self.root.bind_all("<Button-5>", self.on_linux_scroll_down, add="+")
        self.root.bind_all("<Up>", self.on_arrow_up, add="+")
        self.root.bind_all("<Down>", self.on_arrow_down, add="+")
        self.root.bind_all("<Prior>", self.on_page_up, add="+")
        self.root.bind_all("<Next>", self.on_page_down, add="+")

    def active_scrollable(self):
        frame = self.page_frames.get(self.active_page)
        if frame is None:
            return None
        return frame

    def focused_widget_class(self) -> str:
        try:
            widget = self.root.focus_get()
            if widget is None:
                return ""
            return str(widget.winfo_class()).lower()
        except Exception:
            return ""

    def should_preserve_arrow_key(self) -> bool:
        widget_class = self.focused_widget_class()
        return any(name in widget_class for name in ("entry", "text", "listbox", "spinbox"))

    def scroll_active(self, units: int, axis: str = "y", what: str = "units") -> str:
        scrollable = self.active_scrollable()
        if scrollable is None:
            return "break"
        try:
            canvas = scrollable._parent_canvas
            if axis == "x":
                canvas.xview_scroll(units, what)
            else:
                canvas.yview_scroll(units, what)
        except Exception:
            return "break"
        return "break"

    def on_mousewheel(self, event) -> str:
        if sys.platform == "darwin":
            delta = -1 * int(event.delta)
            if delta == 0:
                delta = -1 if event.delta > 0 else 1
            return self.scroll_active(delta)
        step = -1 * int(event.delta / 120) if event.delta else 0
        if step == 0:
            step = -1 if event.delta > 0 else 1
        return self.scroll_active(step)

    def on_shift_mousewheel(self, event) -> str:
        if sys.platform == "darwin":
            delta = -1 * int(event.delta)
            if delta == 0:
                delta = -1 if event.delta > 0 else 1
            return self.scroll_active(delta, axis="x")
        step = -1 * int(event.delta / 120) if event.delta else 0
        if step == 0:
            step = -1 if event.delta > 0 else 1
        return self.scroll_active(step, axis="x")

    def on_linux_scroll_up(self, _event) -> str:
        return self.scroll_active(-3)

    def on_linux_scroll_down(self, _event) -> str:
        return self.scroll_active(3)

    def on_arrow_up(self, _event) -> str | None:
        if self.should_preserve_arrow_key():
            return None
        return self.scroll_active(-2)

    def on_arrow_down(self, _event) -> str | None:
        if self.should_preserve_arrow_key():
            return None
        return self.scroll_active(2)

    def on_page_up(self, _event) -> str | None:
        if self.should_preserve_arrow_key():
            return None
        return self.scroll_active(-1, what="pages")

    def on_page_down(self, _event) -> str | None:
        if self.should_preserve_arrow_key():
            return None
        return self.scroll_active(1, what="pages")

    def build_sidebar(self, parent) -> None:
        brand = ctk.CTkFrame(parent, fg_color="transparent")
        brand.pack(fill="x", padx=18, pady=(24, 20))
        ctk.CTkLabel(
            brand,
            text="Content List Generator",
            font=ctk.CTkFont(size=20, weight="bold"),
            text_color=themed_color("title_fg"),
            wraplength=230,
            justify="left",
        ).pack(anchor="w")
        ctk.CTkLabel(
            brand,
            text="Create file lists, copy email files, and keep a simple record of what was saved.",
            font=ctk.CTkFont(size=13),
            text_color=themed_color("hint_fg"),
            wraplength=220,
            justify="left",
        ).pack(anchor="w", pady=(10, 0))

        nav = ctk.CTkFrame(parent, fg_color="transparent")
        nav.pack(fill="x", padx=16, pady=(4, 0))
        self.nav_buttons["content"] = self.make_nav_button(nav, "Content List", lambda: self.show_page("content"))
        self.nav_buttons["content"].pack(fill="x", pady=4)
        self.nav_buttons["email"] = self.make_nav_button(nav, "Copy Email Files", lambda: self.show_page("email"))
        self.nav_buttons["email"].pack(fill="x", pady=4)
        self.nav_buttons["about"] = self.make_nav_button(nav, "About", lambda: self.show_page("about"))
        self.nav_buttons["about"].pack(fill="x", pady=4)

        footer = ctk.CTkFrame(parent, fg_color=themed_color("card_bg"), corner_radius=18)
        footer.pack(side="bottom", fill="x", padx=16, pady=20)
        ctk.CTkLabel(
            footer,
            text="Appearance",
            font=ctk.CTkFont(size=12, weight="bold"),
            text_color=themed_color("hint_fg"),
        ).pack(anchor="w", padx=16, pady=(16, 6))
        ctk.CTkSwitch(
            footer,
            text="Dark mode",
            variable=self.theme_mode_var,
            onvalue="dark",
            offvalue="light",
            command=self.toggle_theme,
            text_color=themed_color("body_fg"),
            progress_color=themed_color("progress_fill"),
        ).pack(anchor="w", padx=16, pady=(0, 12))
        ctk.CTkLabel(
            footer,
            text="The same tools are available in light and dark mode.",
            font=ctk.CTkFont(size=12),
            text_color=themed_color("hint_fg"),
            wraplength=196,
            justify="left",
        ).pack(anchor="w", padx=16, pady=(0, 16))

    def build_content_page(self, parent) -> ctk.CTkScrollableFrame:
        page = self.build_scrollable_root(parent)
        page.pack_forget()
        page.grid_columnconfigure(0, weight=1)
        page.grid_columnconfigure(1, weight=1)

        hero = ctk.CTkFrame(page, fg_color=themed_color("hero_bg"), corner_radius=24)
        hero.grid(row=0, column=0, columnspan=2, sticky="ew", padx=28, pady=(28, 0))
        hero.grid_columnconfigure(0, weight=1)
        ctk.CTkLabel(
            hero,
            text="Content List Generator",
            font=ctk.CTkFont(size=36, weight="bold"),
            text_color=themed_color("hero_fg"),
        ).grid(row=0, column=0, sticky="w", padx=28, pady=(24, 0))
        ctk.CTkLabel(
            hero,
            text=(
                "Create a simple file list from a folder, save an Excel copy if you want one, "
                "or launch the email-copy flow when you need to gather supported email files."
            ),
            font=ctk.CTkFont(size=14),
            text_color=themed_color("hero_muted"),
            wraplength=780,
            justify="left",
        ).grid(row=1, column=0, sticky="w", padx=28, pady=(10, 24))

        source_card = self.make_field_card(page, "Folder to scan", self.source_var, self.choose_source, hint="Choose the folder you want the app to scan.")
        source_card.grid(row=1, column=0, sticky="nsew", padx=(28, 10), pady=(22, 0))
        self.source_entry = source_card.entry
        output_card = self.make_field_card(page, "Save results to", self.output_dir_var, self.choose_output, hint="Choose where the CSV file should be saved.")
        output_card.grid(row=1, column=1, sticky="nsew", padx=(10, 28), pady=(22, 0))
        self.output_entry = output_card.entry

        naming_card = ctk.CTkFrame(page, fg_color=themed_color("card_bg"), corner_radius=22)
        naming_card.grid(row=2, column=0, columnspan=2, sticky="ew", padx=28, pady=(18, 0))
        naming_card.grid_columnconfigure((0, 1), weight=1)
        ctk.CTkLabel(naming_card, text="Output details", font=ctk.CTkFont(size=20, weight="bold"), text_color=themed_color("body_fg")).grid(row=0, column=0, columnspan=2, sticky="w", padx=24, pady=(20, 12))
        file_card = self.make_text_field_card(naming_card, "Name for the saved list", self.output_name_var, hint="The file name should end in .csv.")
        file_card.grid(row=1, column=0, sticky="ew", padx=(24, 10), pady=(0, 20))
        self.file_entry = file_card.entry
        exclude_card = self.make_text_field_card(naming_card, "Skip file types (optional)", self.exclude_var, hint="Example: tmp,log,bak")
        exclude_card.grid(row=1, column=1, sticky="ew", padx=(10, 24), pady=(0, 20))
        self.exclude_entry = exclude_card.entry

        options_wrap = ctk.CTkFrame(page, fg_color="transparent")
        options_wrap.grid(row=3, column=0, columnspan=2, sticky="ew", padx=28, pady=(18, 0))
        options_wrap.grid_columnconfigure((0, 1), weight=1)
        ctk.CTkLabel(options_wrap, text="Options", font=ctk.CTkFont(size=20, weight="bold"), text_color=themed_color("body_fg")).grid(row=0, column=0, sticky="w", pady=(0, 10))
        ctk.CTkLabel(options_wrap, text="Choose any extras you want before you generate the file list.", font=ctk.CTkFont(size=13), text_color=themed_color("hint_fg")).grid(row=1, column=0, columnspan=2, sticky="w", pady=(0, 14))

        self.make_option_tile(options_wrap, "Add SHA-256 hashes (advanced)", self.hash_var).grid(row=2, column=0, sticky="ew", padx=(0, 10), pady=(0, 10))
        self.make_option_tile(options_wrap, "Skip hidden files", self.hidden_var).grid(row=2, column=1, sticky="ew", padx=(10, 0), pady=(0, 10))
        self.make_option_tile(options_wrap, "Skip common system files", self.system_var).grid(row=3, column=0, sticky="ew", padx=(0, 10), pady=(0, 10))
        self.make_option_tile(options_wrap, "Also save an Excel copy", self.xlsx_var, command=self.sync_xlsx_state).grid(row=3, column=1, sticky="ew", padx=(10, 0), pady=(0, 10))
        preserve_tile = self.make_option_tile(options_wrap, "Keep leading zeros in Excel", self.preserve_zeros_var)
        preserve_tile.grid(row=4, column=0, sticky="ew", padx=(0, 10), pady=(0, 10))
        self.preserve_zeros_toggle = preserve_tile.checkbox

        actions = ctk.CTkFrame(page, fg_color="transparent")
        actions.grid(row=4, column=0, columnspan=2, sticky="ew", padx=28, pady=(18, 0))
        self.generate_button = self.make_primary_button(actions, "Generate Content List", self.start_scan)
        self.generate_button.pack(side="left")
        self.email_button = self.make_secondary_button(actions, "Copy Email Files", self.open_email_copy_window)
        self.email_button.pack(side="left", padx=(10, 0))
        self.make_secondary_button(actions, "Use Source As Output", self.copy_source_to_output).pack(side="left", padx=(10, 0))
        self.reset_button = self.make_secondary_button(actions, "Reset", self.reset_fields)
        self.reset_button.pack(side="left", padx=(10, 0))
        self.open_folder_button = self.make_secondary_button(actions, "Open Output Folder", self.open_output_folder)
        self.open_folder_button.pack(side="left", padx=(10, 0))

        progress_card = ctk.CTkFrame(page, fg_color=themed_color("card_bg"), corner_radius=22)
        progress_card.grid(row=5, column=0, columnspan=2, sticky="ew", padx=28, pady=(18, 0))
        progress_card.grid_columnconfigure((0, 1, 2), weight=1)
        ctk.CTkLabel(progress_card, text="Progress", font=ctk.CTkFont(size=20, weight="bold"), text_color=themed_color("body_fg")).grid(row=0, column=0, sticky="w", padx=24, pady=(20, 10))
        metric_row = ctk.CTkFrame(progress_card, fg_color="transparent")
        metric_row.grid(row=1, column=0, columnspan=3, sticky="ew", padx=24, pady=(0, 14))
        metric_row.grid_columnconfigure((0, 1, 2), weight=1)
        self.make_metric_card(metric_row, "Files Included", self.scan_files_var, accent=True).grid(row=0, column=0, sticky="ew", padx=(0, 8))
        self.make_metric_card(metric_row, "Items Skipped", self.scan_skipped_var).grid(row=0, column=1, sticky="ew", padx=4)
        self.make_metric_card(metric_row, "Saved Output", self.scan_saved_var).grid(row=0, column=2, sticky="ew", padx=(8, 0))

        self.progress = ctk.CTkProgressBar(progress_card, progress_color=themed_color("progress_fill"), mode="determinate")
        self.progress.grid(row=2, column=0, columnspan=3, sticky="ew", padx=24)
        self.progress.set(0)
        ctk.CTkLabel(progress_card, textvariable=self.status_var, text_color=themed_color("body_fg"), wraplength=940, justify="left").grid(row=3, column=0, columnspan=3, sticky="w", padx=24, pady=(12, 18))

        summary_card = ctk.CTkFrame(page, fg_color=themed_color("card_bg"), corner_radius=22)
        summary_card.grid(row=6, column=0, columnspan=2, sticky="nsew", padx=28, pady=(18, 28))
        summary_card.grid_columnconfigure(0, weight=1)
        ctk.CTkLabel(summary_card, text="Summary", font=ctk.CTkFont(size=20, weight="bold"), text_color=themed_color("body_fg")).grid(row=0, column=0, sticky="w", padx=24, pady=(20, 10))
        self.summary = ctk.CTkTextbox(
            summary_card,
            height=280,
            wrap="word",
            fg_color=themed_color("card_alt_bg"),
            text_color=themed_color("body_fg"),
            border_width=0,
            font=("Menlo", 11),
        )
        self.summary.grid(row=1, column=0, sticky="nsew", padx=24, pady=(0, 24))
        return page

    def build_email_page(self, parent) -> ctk.CTkScrollableFrame:
        self.email_page = EmailCopyPage(self, parent)
        return self.email_page.page

    def build_about_page(self, parent) -> ctk.CTkScrollableFrame:
        page = self.build_scrollable_root(parent)
        page.pack_forget()
        page.grid_columnconfigure(0, weight=1)

        card = ctk.CTkFrame(page, fg_color=themed_color("card_bg"), corner_radius=24)
        card.grid(row=0, column=0, sticky="ew", padx=28, pady=28)
        ctk.CTkLabel(card, text="About Content List Generator", font=ctk.CTkFont(size=32, weight="bold"), text_color=themed_color("title_fg")).pack(anchor="w", padx=28, pady=(26, 0))
        ctk.CTkLabel(
            card,
            text=(
                "Content List Generator helps you create a simple file list from a folder and "
                "copy supported email files into a new location."
            ),
            font=ctk.CTkFont(size=14),
            text_color=themed_color("hint_fg"),
            wraplength=920,
            justify="left",
        ).pack(anchor="w", padx=28, pady=(10, 20))
        details = ctk.CTkFrame(card, fg_color=themed_color("card_alt_bg"), corner_radius=18)
        details.pack(fill="x", padx=28, pady=(0, 18))
        ctk.CTkLabel(details, text="Written by Bryan Snyder", font=ctk.CTkFont(size=16, weight="bold"), text_color=themed_color("body_fg")).pack(anchor="w", padx=20, pady=(18, 6))
        ctk.CTkLabel(details, text=f"GitHub: {PLACEHOLDER_GITHUB_URL}", text_color=themed_color("body_fg"), wraplength=860, justify="left").pack(anchor="w", padx=20)
        self.make_secondary_button(details, "Open GitHub Link", lambda: webbrowser.open_new_tab(PLACEHOLDER_GITHUB_URL)).pack(anchor="w", padx=20, pady=(12, 18))

        open_source = ctk.CTkFrame(card, fg_color=themed_color("card_alt_bg"), corner_radius=18)
        open_source.pack(fill="x", padx=28, pady=(0, 28))
        ctk.CTkLabel(open_source, text="Open source note", font=ctk.CTkFont(size=18, weight="bold"), text_color=themed_color("body_fg")).pack(anchor="w", padx=20, pady=(18, 8))
        ctk.CTkLabel(
            open_source,
            text=(
                "This project is being prepared for an open source release.\n"
                "TODO: decide the final attribution requirement before publishing."
            ),
            text_color=themed_color("body_fg"),
            wraplength=860,
            justify="left",
        ).pack(anchor="w", padx=20, pady=(0, 18))
        return page

    def focus_source_entry(self) -> None:
        if self.source_entry is not None and self.source_entry.winfo_exists():
            self.source_entry.focus_force()
            self.source_entry.icursor("end")

    def make_primary_button(self, parent, text: str, command) -> ctk.CTkButton:
        return ctk.CTkButton(
            parent,
            text=text,
            command=command,
            fg_color=themed_color("primary_bg"),
            hover_color=themed_color("progress_fill"),
            text_color=themed_color("primary_fg"),
            corner_radius=12,
            height=44,
            font=ctk.CTkFont(size=14, weight="bold"),
        )

    def make_secondary_button(self, parent, text: str, command) -> ctk.CTkButton:
        return ctk.CTkButton(
            parent,
            text=text,
            command=command,
            fg_color=themed_color("secondary_bg"),
            hover_color=themed_color("secondary_hover"),
            text_color=themed_color("secondary_fg"),
            border_color=themed_color("secondary_bg"),
            border_width=0,
            corner_radius=12,
            height=44,
            font=ctk.CTkFont(size=13, weight="bold"),
        )

    def make_nav_button(self, parent, text: str, command) -> ctk.CTkButton:
        return ctk.CTkButton(
            parent,
            text=text,
            command=command,
            anchor="w",
            height=46,
            corner_radius=14,
            fg_color="transparent",
            hover_color=themed_color("card_bg"),
            text_color=themed_color("sidebar_idle_fg"),
            font=ctk.CTkFont(size=15, weight="bold"),
        )

    def make_metric_card(self, parent, title: str, value_var: tk.StringVar, accent: bool = False) -> ctk.CTkFrame:
        frame = ctk.CTkFrame(parent, fg_color=themed_color("card_alt_bg"), corner_radius=18)
        ctk.CTkLabel(
            frame,
            text=title,
            font=ctk.CTkFont(size=11, weight="bold"),
            text_color=themed_color("hint_fg"),
            anchor="w",
            justify="left",
            wraplength=130,
        ).pack(fill="x", padx=16, pady=(14, 6))
        ctk.CTkLabel(
            frame,
            textvariable=value_var,
            font=ctk.CTkFont(size=22, weight="bold"),
            text_color=themed_color("progress_fill" if accent else "body_fg"),
            anchor="w",
            justify="left",
        ).pack(fill="x", padx=16, pady=(0, 14))
        return frame

    def make_option_tile(self, parent, text: str, variable: tk.BooleanVar, command=None) -> ctk.CTkFrame:
        tile = ctk.CTkFrame(parent, fg_color=themed_color("card_bg"), corner_radius=18)
        checkbox = ctk.CTkCheckBox(
            tile,
            text=text,
            variable=variable,
            command=command,
            text_color=themed_color("body_fg"),
            fg_color=themed_color("primary_bg"),
            hover_color=themed_color("primary_hover"),
            border_color=themed_color("border"),
            checkmark_color=themed_color("primary_fg"),
            corner_radius=8,
        )
        checkbox.pack(anchor="w", padx=16, pady=16)
        tile.checkbox = checkbox
        return tile

    def make_field_card(self, parent, label: str, variable: tk.StringVar, command, hint: str = "") -> ctk.CTkFrame:
        card = ctk.CTkFrame(parent, fg_color=themed_color("card_bg"), corner_radius=22)
        card.grid_columnconfigure(0, weight=1)
        ctk.CTkLabel(card, text=label, font=ctk.CTkFont(size=18, weight="bold"), text_color=themed_color("body_fg")).grid(row=0, column=0, sticky="w", padx=22, pady=(20, 6))
        if hint:
            ctk.CTkLabel(card, text=hint, font=ctk.CTkFont(size=12), text_color=themed_color("hint_fg"), wraplength=420, justify="left").grid(row=1, column=0, sticky="w", padx=22, pady=(0, 12))
        row_idx = 2 if hint else 1
        entry_wrap = ctk.CTkFrame(card, fg_color="transparent")
        entry_wrap.grid(row=row_idx, column=0, sticky="ew", padx=22, pady=(0, 20))
        entry_wrap.grid_columnconfigure(0, weight=1)
        entry = ctk.CTkEntry(
            entry_wrap,
            textvariable=variable,
            fg_color=themed_color("entry_bg"),
            text_color=themed_color("entry_fg"),
            border_color=themed_color("border"),
            height=44,
        )
        entry.grid(row=0, column=0, sticky="ew")
        self.make_secondary_button(entry_wrap, "Browse", command).grid(row=0, column=1, padx=(12, 0))
        card.entry = entry
        return card

    def make_text_field_card(self, parent, label: str, variable: tk.StringVar, hint: str = "") -> ctk.CTkFrame:
        card = ctk.CTkFrame(parent, fg_color=themed_color("card_alt_bg"), corner_radius=18)
        card.grid_columnconfigure(0, weight=1)
        ctk.CTkLabel(card, text=label, font=ctk.CTkFont(size=15, weight="bold"), text_color=themed_color("body_fg")).grid(row=0, column=0, sticky="w", padx=18, pady=(18, 6))
        entry = ctk.CTkEntry(
            card,
            textvariable=variable,
            fg_color=themed_color("entry_bg"),
            text_color=themed_color("entry_fg"),
            border_color=themed_color("border"),
            height=42,
        )
        entry.grid(row=1, column=0, sticky="ew", padx=18)
        if hint:
            ctk.CTkLabel(card, text=hint, font=ctk.CTkFont(size=12), text_color=themed_color("hint_fg"), wraplength=420, justify="left").grid(row=2, column=0, sticky="w", padx=18, pady=(8, 18))
        else:
            ctk.CTkFrame(card, fg_color="transparent", height=18).grid(row=2, column=0)
        card.entry = entry
        return card

    def toggle_theme(self) -> None:
        self.colors = palette_for_mode(self.theme_mode_var.get())
        save_theme_mode(self.theme_mode_var.get())
        ctk.set_appearance_mode(self.theme_mode_var.get())
        self.root.configure(fg_color=themed_color("app_bg"))
        self.configure_style()
        self.show_page(self.active_page)

    def show_page(self, page: str) -> None:
        self.active_page = page
        for name, frame in self.page_frames.items():
            if name == page:
                frame.pack(fill="both", expand=True)
            else:
                frame.pack_forget()
        for name, button in self.nav_buttons.items():
            if name == page:
                button.configure(
                    fg_color=themed_color("sidebar_active_bg"),
                    hover_color=themed_color("sidebar_active_bg"),
                    text_color=themed_color("sidebar_active_fg"),
                )
            else:
                button.configure(
                    fg_color="transparent",
                    hover_color=themed_color("card_bg"),
                    text_color=themed_color("sidebar_idle_fg"),
                )
        if page == "content":
            self.root.after(50, self.focus_source_entry)

    def sync_xlsx_state(self) -> None:
        state = "normal" if self.xlsx_var.get() else "disabled"
        if self.preserve_zeros_toggle is not None:
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
        self.hash_var.set(True)
        self.hidden_var.set(False)
        self.system_var.set(False)
        self.xlsx_var.set(True)
        self.preserve_zeros_var.set(True)
        if self.progress is not None:
            self.progress.set(0)
        self.status_var.set("Choose a folder to scan, then click Generate Content List.")
        self.scan_files_var.set("0")
        self.scan_skipped_var.set("0")
        self.scan_saved_var.set("Waiting")
        self.append_summary("")
        self.sync_xlsx_state()
        self.show_page("content")
        self.focus_source_entry()

    def show_about_dialog(self) -> None:
        self.show_page("about")

    def open_email_copy_window(self) -> None:
        if self.running:
            return
        self.show_page("email")
        email_page = getattr(self, "email_page", None)
        if email_page is not None:
            self.root.after(50, email_page.focus_source_entry)

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
        if self.progress is not None:
            self.progress.set(0)
        self.status_var.set("Getting everything ready...")
        self.scan_files_var.set("0")
        self.scan_skipped_var.set("0")
        self.scan_saved_var.set("Working")
        self.append_summary("Preparing your file list...")
        self.show_page("content")

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
                    if self.progress is not None:
                        self.progress.set(0)
                elif kind == "status":
                    self.status_var.set(str(payload))
                elif kind == "progress":
                    current, total, name = payload
                    if self.progress is not None:
                        self.progress.set(current / max(1, total))
                    self.status_var.set(f"Working... {current} of {total}: {name}")
                elif kind == "done":
                    self.running = False
                    result = payload
                    self.status_var.set(f"Your file list is ready. {result.files} files were included.")
                    self.scan_files_var.set(str(result.files))
                    self.scan_skipped_var.set(str(result.filtered))
                    self.scan_saved_var.set("CSV" if not result.xlsx_path else "CSV + Excel")
                    self.append_summary(build_scan_summary(result))
                    if self.progress is not None:
                        self.progress.set(1)
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

    if not args.cli and not has_explicit_cli_args:
        if tk is None:
            print("Tkinter is not available on this system.", file=sys.stderr)
            return 1
        if ctk is None:
            print("customtkinter is required for the desktop GUI. Install it with: pip install -r requirements.txt", file=sys.stderr)
            return 1
        return ContentListApp().run()

    if args.mode == "email-copy":
        return run_cli_email_copy(args)
    return run_cli_scan(args)


if __name__ == "__main__":
    raise SystemExit(main())
