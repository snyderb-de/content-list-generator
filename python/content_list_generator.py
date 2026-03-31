#!/usr/bin/env python3

from __future__ import annotations

import argparse
import csv
import hashlib
import os
import queue
import shutil
import sys
import threading
import time
import zipfile
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from pathlib import Path
from typing import Callable
from xml.sax.saxutils import escape

try:
    import tkinter as tk
    from tkinter import filedialog, messagebox, ttk
except Exception:  # pragma: no cover
    tk = None
    filedialog = None
    messagebox = None
    ttk = None


SYSTEM_FILES = {".ds_store", "thumbs.db", "desktop.ini", "ehthumbs.db"}
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
REPORT_HEADERS = [
    "File Name",
    "Extension",
    "Size in Bytes",
    "Size in Human Readable",
    "Path From Root Folder",
    "SHA256 Hash",
]
EMAIL_MANIFEST_HEADERS = [
    "Source Path",
    "Destination Path",
    "Relative Path",
    "File Name",
    "Extension",
    "Size in Bytes",
]


@dataclass
class SummaryEntry:
    label: str
    count: int
    bytes: int


@dataclass
class ScanResult:
    output_path: Path
    xlsx_path: Path | None
    files: int
    total_bytes: int
    filtered: int
    filtered_hidden: int
    filtered_system: int
    filtered_exts: int
    elapsed: float
    hashing: bool
    create_xlsx: bool
    preserve_zeros: bool
    hash_workers: int
    top_by_count: list[SummaryEntry]
    top_by_size: list[SummaryEntry]


@dataclass
class EmailCopyResult:
    source_dir: Path
    dest_dir: Path
    manifest_path: Path
    copied: int
    elapsed: float


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


def default_manifest_name() -> str:
    return f"email-copy-manifest-{time.strftime('%Y-%m-%dT%H-%M-%S')}.csv"


def normalize_extension(path: Path) -> str:
    return path.suffix.lower().lstrip(".")


def summary_key(ext: str) -> str:
    return f".{ext}" if ext else "[no extension]"


def is_hidden_path(path: Path, source_root: Path) -> bool:
    relative = path.relative_to(source_root)
    return any(part.startswith(".") for part in relative.parts)


def should_skip(
    path: Path,
    source_root: Path,
    include_hidden: bool,
    include_system: bool,
    excluded_exts: set[str],
) -> tuple[str, bool]:
    if not include_hidden and is_hidden_path(path, source_root):
        return "hidden path", True
    if not include_system and path.name.lower() in SYSTEM_FILES:
        return "system file", True
    if normalize_extension(path) in excluded_exts:
        return "excluded extension", True
    return "", False


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


def collect_files(
    source_dir: Path,
    include_hidden: bool,
    include_system: bool,
    excluded_exts: set[str],
) -> tuple[list[Path], int, int, int, int]:
    kept: list[Path] = []
    filtered = 0
    filtered_hidden = 0
    filtered_system = 0
    filtered_exts = 0

    for root, dirs, files in os.walk(source_dir):
        root_path = Path(root)
        if not include_hidden:
            visible_dirs = []
            for directory in dirs:
                candidate = root_path / directory
                if is_hidden_path(candidate, source_dir):
                    filtered += 1
                    filtered_hidden += 1
                    continue
                visible_dirs.append(directory)
            dirs[:] = visible_dirs

        for file_name in sorted(files):
            candidate = root_path / file_name
            reason, skipped = should_skip(candidate, source_dir, include_hidden, include_system, excluded_exts)
            if skipped:
                filtered += 1
                if reason == "hidden path":
                    filtered_hidden += 1
                elif reason == "system file":
                    filtered_system += 1
                elif reason == "excluded extension":
                    filtered_exts += 1
                continue
            kept.append(candidate)

    kept.sort()
    return kept, filtered, filtered_hidden, filtered_system, filtered_exts


def summarize_entries(summaries: dict[str, dict[str, int]], key: str) -> list[SummaryEntry]:
    entries = [
        SummaryEntry(label=label, count=data["count"], bytes=data["bytes"])
        for label, data in summaries.items()
    ]
    if key == "count":
        entries.sort(key=lambda item: (-item.count, -item.bytes, item.label))
    else:
        entries.sort(key=lambda item: (-item.bytes, -item.count, item.label))
    return entries[:8]


def write_csv_report(
    source_dir: Path,
    output_path: Path,
    files: list[Path],
    hashing: bool,
    progress_callback: Callable[[int, int, Path], None] | None = None,
) -> tuple[int, int, dict[str, dict[str, int]], int]:
    summaries: dict[str, dict[str, int]] = {}
    total_bytes = 0
    hash_workers = 1
    output_path.parent.mkdir(parents=True, exist_ok=True)

    with output_path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.writer(handle)
        writer.writerow(REPORT_HEADERS)

        if hashing:
            hash_workers = max(2, os.cpu_count() or 2)
            with ThreadPoolExecutor(max_workers=hash_workers) as pool:
                iterator = pool.map(hash_file, files)
                for index, (file_path, file_hash) in enumerate(zip(files, iterator), start=1):
                    stat = file_path.stat()
                    size = stat.st_size
                    total_bytes += size
                    ext = normalize_extension(file_path)
                    bucket = summaries.setdefault(summary_key(ext), {"count": 0, "bytes": 0})
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
                    if progress_callback is not None:
                        progress_callback(index, len(files), file_path)
        else:
            for index, file_path in enumerate(files, start=1):
                stat = file_path.stat()
                size = stat.st_size
                total_bytes += size
                ext = normalize_extension(file_path)
                bucket = summaries.setdefault(summary_key(ext), {"count": 0, "bytes": 0})
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
                if progress_callback is not None:
                    progress_callback(index, len(files), file_path)

    return len(files), total_bytes, summaries, hash_workers


def _xlsx_col_name(index: int) -> str:
    name = ""
    while index > 0:
        index, remainder = divmod(index - 1, 26)
        name = chr(ord("A") + remainder) + name
    return name


def _xlsx_cell_ref(row_index: int, col_index: int) -> str:
    return f"{_xlsx_col_name(col_index)}{row_index}"


def _xlsx_inline_cell(ref: str, value: str, style_id: int = 0) -> str:
    style_attr = f' s="{style_id}"' if style_id else ""
    return f'<c r="{ref}" t="inlineStr"{style_attr}><is><t>{escape(value)}</t></is></c>'


def _xlsx_number_cell(ref: str, value: str, style_id: int = 0) -> str:
    style_attr = f' s="{style_id}"' if style_id else ""
    return f'<c r="{ref}"{style_attr}><v>{escape(value)}</v></c>'


def _build_sheet_xml(rows: list[list[str]], preserve_zeros: bool) -> str:
    xml_rows: list[str] = []
    for row_index, row in enumerate(rows, start=1):
        cells: list[str] = []
        for col_index, value in enumerate(row, start=1):
            ref = _xlsx_cell_ref(row_index, col_index)
            if preserve_zeros:
                cells.append(_xlsx_inline_cell(ref, value, style_id=1))
            elif row_index > 1 and col_index == 3 and value.isdigit():
                cells.append(_xlsx_number_cell(ref, value))
            else:
                cells.append(_xlsx_inline_cell(ref, value))
        xml_rows.append(f'<row r="{row_index}">{"".join(cells)}</row>')
    dimension = "A1"
    if rows and rows[0]:
        dimension = f"A1:{_xlsx_cell_ref(len(rows), len(rows[0]))}"
    return (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        '<worksheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main" '
        'xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships">'
        f"<dimension ref=\"{dimension}\"/>"
        '<sheetViews><sheetView workbookViewId="0"/></sheetViews>'
        "<sheetFormatPr defaultRowHeight=\"15\"/>"
        f"<sheetData>{''.join(xml_rows)}</sheetData>"
        "</worksheet>"
    )


def convert_csv_to_xlsx(csv_path: Path, xlsx_path: Path, preserve_zeros: bool) -> None:
    with csv_path.open("r", newline="", encoding="utf-8") as handle:
        rows = list(csv.reader(handle))

    xlsx_path.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(xlsx_path, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        archive.writestr(
            "[Content_Types].xml",
            """<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">
  <Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>
  <Default Extension="xml" ContentType="application/xml"/>
  <Override PartName="/xl/workbook.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet.main+xml"/>
  <Override PartName="/xl/worksheets/sheet1.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.worksheet+xml"/>
  <Override PartName="/xl/styles.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.styles+xml"/>
  <Override PartName="/docProps/core.xml" ContentType="application/vnd.openxmlformats-package.core-properties+xml"/>
  <Override PartName="/docProps/app.xml" ContentType="application/vnd.openxmlformats-officedocument.extended-properties+xml"/>
</Types>""",
        )
        archive.writestr(
            "_rels/.rels",
            """<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">
  <Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" Target="xl/workbook.xml"/>
  <Relationship Id="rId2" Type="http://schemas.openxmlformats.org/package/2006/relationships/metadata/core-properties" Target="docProps/core.xml"/>
  <Relationship Id="rId3" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/extended-properties" Target="docProps/app.xml"/>
</Relationships>""",
        )
        archive.writestr(
            "docProps/core.xml",
            """<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<cp:coreProperties xmlns:cp="http://schemas.openxmlformats.org/package/2006/metadata/core-properties" xmlns:dc="http://purl.org/dc/elements/1.1/" xmlns:dcterms="http://purl.org/dc/terms/" xmlns:dcmitype="http://purl.org/dc/dcmitype/" xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance">
  <dc:title>Content List Generator</dc:title>
</cp:coreProperties>""",
        )
        archive.writestr(
            "docProps/app.xml",
            """<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<Properties xmlns="http://schemas.openxmlformats.org/officeDocument/2006/extended-properties" xmlns:vt="http://schemas.openxmlformats.org/officeDocument/2006/docPropsVTypes">
  <Application>Content List Generator</Application>
</Properties>""",
        )
        archive.writestr(
            "xl/workbook.xml",
            """<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<workbook xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main" xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships">
  <sheets>
    <sheet name="Sheet1" sheetId="1" r:id="rId1"/>
  </sheets>
</workbook>""",
        )
        archive.writestr(
            "xl/_rels/workbook.xml.rels",
            """<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">
  <Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/worksheet" Target="worksheets/sheet1.xml"/>
  <Relationship Id="rId2" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/styles" Target="styles.xml"/>
</Relationships>""",
        )
        archive.writestr(
            "xl/styles.xml",
            """<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<styleSheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main">
  <numFmts count="1">
    <numFmt numFmtId="49" formatCode="@"/>
  </numFmts>
  <fonts count="1">
    <font><sz val="11"/><name val="Calibri"/></font>
  </fonts>
  <fills count="2">
    <fill><patternFill patternType="none"/></fill>
    <fill><patternFill patternType="gray125"/></fill>
  </fills>
  <borders count="1">
    <border><left/><right/><top/><bottom/><diagonal/></border>
  </borders>
  <cellStyleXfs count="1">
    <xf numFmtId="0" fontId="0" fillId="0" borderId="0"/>
  </cellStyleXfs>
  <cellXfs count="2">
    <xf numFmtId="0" fontId="0" fillId="0" borderId="0" xfId="0"/>
    <xf numFmtId="49" fontId="0" fillId="0" borderId="0" xfId="0" applyNumberFormat="1"/>
  </cellXfs>
  <cellStyles count="1">
    <cellStyle name="Normal" xfId="0" builtinId="0"/>
  </cellStyles>
</styleSheet>""",
        )
        archive.writestr("xl/worksheets/sheet1.xml", _build_sheet_xml(rows, preserve_zeros))


def render_top(title: str, entries: list[SummaryEntry], by_size: bool = False) -> list[str]:
    lines = [title]
    for entry in entries:
        if by_size:
            lines.append(f"  {entry.label}: {human_bytes(entry.bytes)}, {entry.count} files")
        else:
            lines.append(f"  {entry.label}: {entry.count} files, {human_bytes(entry.bytes)}")
    if len(lines) == 1:
        lines.append("  No files were written.")
    return lines


def run_scan(
    source_dir: Path,
    output_path: Path,
    *,
    hashing: bool,
    include_hidden: bool,
    include_system: bool,
    excluded_exts: set[str],
    create_xlsx: bool,
    preserve_zeros: bool,
    progress_callback: Callable[[int, int, Path], None] | None = None,
) -> ScanResult:
    started = time.time()
    files, filtered, filtered_hidden, filtered_system, filtered_exts = collect_files(
        source_dir,
        include_hidden,
        include_system,
        excluded_exts,
    )
    file_count, total_bytes, summaries, hash_workers = write_csv_report(
        source_dir,
        output_path,
        files,
        hashing,
        progress_callback=progress_callback,
    )
    xlsx_path: Path | None = None
    if create_xlsx:
        xlsx_path = output_path.with_suffix(".xlsx")
        convert_csv_to_xlsx(output_path, xlsx_path, preserve_zeros)
    return ScanResult(
        output_path=output_path,
        xlsx_path=xlsx_path,
        files=file_count,
        total_bytes=total_bytes,
        filtered=filtered,
        filtered_hidden=filtered_hidden,
        filtered_system=filtered_system,
        filtered_exts=filtered_exts,
        elapsed=time.time() - started,
        hashing=hashing,
        create_xlsx=create_xlsx,
        preserve_zeros=preserve_zeros,
        hash_workers=hash_workers,
        top_by_count=summarize_entries(summaries, "count"),
        top_by_size=summarize_entries(summaries, "bytes"),
    )


def collect_email_matches(source_dir: Path) -> list[Path]:
    matches = [path for path in source_dir.rglob("*") if path.is_file() and path.suffix.lower() in EMAIL_EXTENSIONS]
    matches.sort()
    return matches


def copy_email_files(source_dir: Path, dest_dir: Path) -> EmailCopyResult:
    if not source_dir.is_dir():
        raise ValueError(f"Source folder does not exist: {source_dir}")

    started = time.time()
    dest_dir.mkdir(parents=True, exist_ok=True)
    manifest_path = dest_dir / default_manifest_name()
    matches = collect_email_matches(source_dir)
    copied = 0

    with manifest_path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.writer(handle)
        writer.writerow(EMAIL_MANIFEST_HEADERS)

        for path in matches:
            relative = path.relative_to(source_dir)
            target = dest_dir / relative
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(path, target)
            writer.writerow(
                [
                    str(path),
                    str(target),
                    relative.as_posix(),
                    path.name,
                    path.suffix.lower(),
                    str(path.stat().st_size),
                ]
            )
            copied += 1

    return EmailCopyResult(
        source_dir=source_dir,
        dest_dir=dest_dir,
        manifest_path=manifest_path,
        copied=copied,
        elapsed=time.time() - started,
    )


def build_scan_summary(result: ScanResult) -> str:
    lines = [
        "Done",
        f"Output: {result.output_path}",
        f"XLSX copy: {result.xlsx_path if result.xlsx_path else 'not created'}",
        f"Files: {result.files}",
        f"Bytes: {result.total_bytes} ({human_bytes(result.total_bytes)})",
        f"Filtered out: {result.filtered}",
        f"Hidden filtered: {result.filtered_hidden}",
        f"System filtered: {result.filtered_system}",
        f"Extension filtered: {result.filtered_exts}",
        f"Hashing: {'on' if result.hashing else 'off'}",
        f"Create XLSX: {'on' if result.create_xlsx else 'off'}",
        f"Preserve zeros: {'on' if result.preserve_zeros and result.create_xlsx else 'off'}",
        f"Hash workers: {result.hash_workers}",
        f"Elapsed: {result.elapsed:.2f}s",
        "",
        *render_top("Top extensions by count", result.top_by_count),
        "",
        *render_top("Top extensions by size", result.top_by_size, by_size=True),
    ]
    return "\n".join(lines)


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
        ttk.Button(actions, text="Start Copy", style="Primary.TButton", command=self.start_copy).pack(side="left")
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
                    result: EmailCopyResult = payload
                    self.parent.status_var.set(
                        f"Email copy complete. Copied {result.copied} files to {result.dest_dir}."
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
        ttk.Button(actions, text="Generate Content List", style="Primary.TButton", command=self.start_scan).pack(side="left")
        ttk.Button(actions, text="Copy Email Files", style="Secondary.TButton", command=self.open_email_copy_window).pack(side="left", padx=(10, 0))
        ttk.Button(actions, text="Use Source As Output", style="Secondary.TButton", command=self.copy_source_to_output).pack(side="left", padx=(10, 0))

        self.progress = ttk.Progressbar(card, style="Modern.Horizontal.TProgressbar", variable=self.progress_var, mode="determinate")
        self.progress.grid(row=6, column=0, columnspan=3, sticky="ew", pady=(10, 8))
        ttk.Label(card, textvariable=self.status_var, style="Body.TLabel").grid(row=7, column=0, columnspan=3, sticky="w")

        ttk.Label(card, text="Summary", style="Body.TLabel").grid(row=8, column=0, sticky="w", pady=(18, 8))
        self.summary = tk.Text(card, height=16, wrap="word", bd=0, bg="#f7fafc", fg="#243746", font=("Consolas", 11))
        self.summary.grid(row=9, column=0, columnspan=3, sticky="nsew")
        card.rowconfigure(9, weight=1)

        self.sync_xlsx_state()

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
            self.message_queue.put(("done", build_scan_summary(result)))
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
