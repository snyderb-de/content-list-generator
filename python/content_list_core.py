from __future__ import annotations

import csv
import hashlib
import os
import shutil
import time
import zipfile
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from pathlib import Path
from typing import Callable
from xml.sax.saxutils import escape


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
    ".olk15message",
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


@dataclass
class EmailCopyProgress:
    phase: str
    matched: int
    copied: int
    total: int
    current_relative: str = ""


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


def is_path_within(candidate: Path, root: Path) -> bool:
    try:
        candidate.relative_to(root)
        return candidate != root
    except ValueError:
        return False


def copy_email_files(
    source_dir: Path,
    dest_dir: Path,
    progress_callback: Callable[[EmailCopyProgress], None] | None = None,
) -> EmailCopyResult:
    if not source_dir.is_dir():
        raise ValueError(f"Source folder does not exist: {source_dir}")
    source_dir = source_dir.resolve()
    dest_dir = dest_dir.resolve()
    if source_dir == dest_dir:
        raise ValueError("Destination folder must be different from the source folder.")
    if is_path_within(dest_dir, source_dir):
        raise ValueError("Destination folder cannot be inside the source folder.")

    started = time.time()
    dest_dir.mkdir(parents=True, exist_ok=True)
    manifest_path = dest_dir / default_manifest_name()
    matches = collect_email_matches(source_dir)
    if progress_callback is not None:
        progress_callback(EmailCopyProgress(phase="copying", matched=len(matches), copied=0, total=len(matches)))
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
            if progress_callback is not None:
                progress_callback(
                    EmailCopyProgress(
                        phase="copying",
                        matched=len(matches),
                        copied=copied,
                        total=len(matches),
                        current_relative=relative.as_posix(),
                    )
                )

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
