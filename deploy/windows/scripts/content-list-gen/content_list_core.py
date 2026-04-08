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

try:
    import blake3
except Exception:  # pragma: no cover
    blake3 = None


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
HASH_ALGORITHM_OFF = "off"
HASH_ALGORITHM_BLAKE3 = "blake3"
HASH_ALGORITHM_SHA1 = "sha1"
HASH_ALGORITHM_SHA256 = "sha256"
REPORT_HEADERS = [
    "File Name",
    "Extension",
    "Size in Bytes",
    "Size in Human Readable",
    "Path From Root Folder",
    "Hash Algorithm",
    "Hash Value",
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
    source_name: str
    output_path: Path
    xlsx_path: Path | None
    report_path: Path
    files: int
    directories: int
    total_bytes: int
    filtered: int
    filtered_hidden: int
    filtered_system: int
    filtered_exts: int
    elapsed: float
    hash_algorithm: str
    create_xlsx: bool
    preserve_zeros: bool
    hash_workers: int
    top_by_count: list[SummaryEntry]
    top_by_size: list[SummaryEntry]
    first_csv_item: str
    last_csv_item: str


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
    scanned: int
    matched: int
    copied: int
    total: int
    current_relative: str = ""
    current_name: str = ""


@dataclass
class ScanProgress:
    phase: str
    files: int
    total_files: int
    directories: int
    total_directories: int
    bytes: int
    total_bytes: int
    filtered: int
    current_name: str = ""


class ScanCanceled(Exception):
    pass


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


def default_hash_algorithm() -> str:
    return HASH_ALGORITHM_BLAKE3


def normalize_hash_algorithm(value: str | None) -> str:
    normalized = str(value or "").strip().lower()
    if normalized in {"", "off", "none"}:
        return HASH_ALGORITHM_OFF
    if normalized in {"blake3", "fast", "fast (blake3)"}:
        return HASH_ALGORITHM_BLAKE3
    if normalized in {"sha1", "sha-1", "medium", "medium (sha-1)"}:
        return HASH_ALGORITHM_SHA1
    if normalized in {"sha256", "sha-256", "strong", "strong (sha-256)"}:
        return HASH_ALGORITHM_SHA256
    return default_hash_algorithm()


def hash_algorithm_label(value: str) -> str:
    normalized = normalize_hash_algorithm(value)
    if normalized == HASH_ALGORITHM_BLAKE3:
        return "Fast (BLAKE3)"
    if normalized == HASH_ALGORITHM_SHA1:
        return "Medium (SHA-1)"
    if normalized == HASH_ALGORITHM_SHA256:
        return "Strong (SHA-256)"
    return "Off"


def hash_algorithm_csv_name(value: str) -> str:
    normalized = normalize_hash_algorithm(value)
    if normalized == HASH_ALGORITHM_BLAKE3:
        return "BLAKE3"
    if normalized == HASH_ALGORITHM_SHA1:
        return "SHA-1"
    if normalized == HASH_ALGORITHM_SHA256:
        return "SHA-256"
    return ""


def hash_algorithm_labels() -> list[str]:
    return [
        hash_algorithm_label(HASH_ALGORITHM_OFF),
        hash_algorithm_label(HASH_ALGORITHM_BLAKE3),
        hash_algorithm_label(HASH_ALGORITHM_SHA1),
        hash_algorithm_label(HASH_ALGORITHM_SHA256),
    ]


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


def hash_file(path: Path, algorithm: str, cancel_event=None) -> str:
    normalized = normalize_hash_algorithm(algorithm)
    if normalized == HASH_ALGORITHM_OFF:
        return ""
    if normalized == HASH_ALGORITHM_BLAKE3:
        if blake3 is None:
            raise RuntimeError("BLAKE3 hashing requires the 'blake3' Python package. Install it with: pip install -r requirements.txt")
        digest = blake3.blake3()
    elif normalized == HASH_ALGORITHM_SHA1:
        digest = hashlib.sha1()
    else:
        digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            if cancel_event is not None and cancel_event.is_set():
                raise ScanCanceled()
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


def folder_display_name(path: Path) -> str:
    name = path.name
    return name or str(path)


def collect_files(
    source_dir: Path,
    include_hidden: bool,
    include_system: bool,
    excluded_exts: set[str],
    progress_callback: Callable[[ScanProgress], None] | None = None,
    cancel_event=None,
) -> tuple[list[Path], int, int, int, int, int, int]:
    kept: list[Path] = []
    filtered = 0
    filtered_hidden = 0
    filtered_system = 0
    filtered_exts = 0
    directories = 0
    total_bytes = 0

    for root, dirs, files in os.walk(source_dir):
        if cancel_event is not None and cancel_event.is_set():
            raise ScanCanceled()
        root_path = Path(root)
        directories += 1
        if progress_callback is not None and directories % 100 == 0:
            progress_callback(
                ScanProgress(
                    phase="counting",
                    files=len(kept),
                    total_files=0,
                    directories=directories,
                    total_directories=0,
                    bytes=0,
                    total_bytes=0,
                    filtered=filtered,
                    current_name=root_path.name,
                )
            )
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
            if cancel_event is not None and cancel_event.is_set():
                raise ScanCanceled()
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
            try:
                total_bytes += candidate.stat().st_size
            except OSError:
                pass
            if progress_callback is not None and len(kept) % 250 == 0:
                progress_callback(
                    ScanProgress(
                        phase="counting",
                        files=len(kept),
                        total_files=0,
                        directories=directories,
                        total_directories=0,
                        bytes=total_bytes,
                        total_bytes=0,
                        filtered=filtered,
                        current_name=file_name,
                    )
                )

    kept.sort()
    if progress_callback is not None:
        progress_callback(
            ScanProgress(
                phase="counting",
                files=len(kept),
                total_files=0,
                directories=directories,
                total_directories=0,
                bytes=total_bytes,
                total_bytes=0,
                filtered=filtered,
            )
        )
    return kept, filtered, filtered_hidden, filtered_system, filtered_exts, directories, total_bytes


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
    hash_algorithm: str,
    total_directories: int,
    filtered: int,
    total_expected_bytes: int,
    progress_callback: Callable[[ScanProgress], None] | None = None,
    cancel_event=None,
) -> tuple[int, int, dict[str, dict[str, int]], int, str, str]:
    summaries: dict[str, dict[str, int]] = {}
    processed_bytes = 0
    first_csv_item = ""
    last_csv_item = ""
    hash_workers = 1
    output_path.parent.mkdir(parents=True, exist_ok=True)
    normalized_algorithm = normalize_hash_algorithm(hash_algorithm)

    with output_path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.writer(handle)
        writer.writerow(REPORT_HEADERS)

        if normalized_algorithm != HASH_ALGORITHM_OFF:
            hash_workers = max(2, os.cpu_count() or 2)
            with ThreadPoolExecutor(max_workers=hash_workers) as pool:
                iterator = pool.map(lambda path: hash_file(path, normalized_algorithm, cancel_event), files)
                for index, (file_path, file_hash) in enumerate(zip(files, iterator), start=1):
                    if cancel_event is not None and cancel_event.is_set():
                        raise ScanCanceled()
                    stat = file_path.stat()
                    size = stat.st_size
                    processed_bytes += size
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
                            hash_algorithm_csv_name(normalized_algorithm),
                            file_hash,
                        ]
                    )
                    if not first_csv_item:
                        first_csv_item = file_path.relative_to(source_dir).as_posix()
                    last_csv_item = file_path.relative_to(source_dir).as_posix()
                    if progress_callback is not None:
                        progress_callback(
                            ScanProgress(
                                phase="scanning",
                                files=index,
                                total_files=len(files),
                                directories=total_directories,
                                total_directories=total_directories,
                                bytes=processed_bytes,
                                total_bytes=total_expected_bytes,
                                filtered=filtered,
                                current_name=file_path.name,
                            )
                        )
        else:
            for index, file_path in enumerate(files, start=1):
                if cancel_event is not None and cancel_event.is_set():
                    raise ScanCanceled()
                stat = file_path.stat()
                size = stat.st_size
                processed_bytes += size
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
                        "",
                    ]
                )
                if not first_csv_item:
                    first_csv_item = file_path.relative_to(source_dir).as_posix()
                last_csv_item = file_path.relative_to(source_dir).as_posix()
                if progress_callback is not None:
                    progress_callback(
                        ScanProgress(
                            phase="scanning",
                            files=index,
                            total_files=len(files),
                            directories=total_directories,
                            total_directories=total_directories,
                            bytes=processed_bytes,
                            total_bytes=total_expected_bytes,
                            filtered=filtered,
                            current_name=file_path.name,
                        )
                    )

    return len(files), processed_bytes, summaries, hash_workers, first_csv_item, last_csv_item


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
    hash_algorithm: str,
    include_hidden: bool,
    include_system: bool,
    excluded_exts: set[str],
    create_xlsx: bool,
    preserve_zeros: bool,
    progress_callback: Callable[[ScanProgress], None] | None = None,
    cancel_event=None,
) -> ScanResult:
    started = time.time()
    xlsx_path: Path | None = None
    report_path = output_path.with_name(f"{output_path.stem}-report.txt")
    try:
        files, filtered, filtered_hidden, filtered_system, filtered_exts, directories, total_expected_bytes = collect_files(
            source_dir,
            include_hidden,
            include_system,
            excluded_exts,
            progress_callback=progress_callback,
            cancel_event=cancel_event,
        )
        file_count, total_bytes, summaries, hash_workers, first_csv_item, last_csv_item = write_csv_report(
            source_dir,
            output_path,
            files,
            hash_algorithm,
            directories,
            filtered,
            total_expected_bytes,
            progress_callback=progress_callback,
            cancel_event=cancel_event,
        )
        if create_xlsx:
            xlsx_path = output_path.with_suffix(".xlsx")
            if cancel_event is not None and cancel_event.is_set():
                raise ScanCanceled()
            convert_csv_to_xlsx(output_path, xlsx_path, preserve_zeros)
        result = ScanResult(
            source_name=folder_display_name(source_dir),
            output_path=output_path,
            xlsx_path=xlsx_path,
            report_path=report_path,
            files=file_count,
            directories=directories,
            total_bytes=total_bytes,
            filtered=filtered,
            filtered_hidden=filtered_hidden,
            filtered_system=filtered_system,
            filtered_exts=filtered_exts,
            elapsed=time.time() - started,
            hash_algorithm=normalize_hash_algorithm(hash_algorithm),
            create_xlsx=create_xlsx,
            preserve_zeros=preserve_zeros,
            hash_workers=hash_workers,
            top_by_count=summarize_entries(summaries, "count"),
            top_by_size=summarize_entries(summaries, "bytes"),
            first_csv_item=first_csv_item,
            last_csv_item=last_csv_item,
        )
        write_scan_report(result)
        return result
    except ScanCanceled:
        for path in (output_path, output_path.with_suffix(".xlsx"), report_path):
            try:
                path.unlink()
            except FileNotFoundError:
                pass
        raise


def write_scan_report(result: ScanResult) -> None:
    result.report_path.write_text(build_scan_report(result), encoding="utf-8")


def build_scan_report(result: ScanResult) -> str:
    lines = [
        "Content List Report",
        f"Selected folder: {result.source_name}",
        f"Saved file list: {result.output_path.name}",
        f"Excel copy: {result.xlsx_path.name if result.xlsx_path else 'not created'}",
        f"Summary report: {result.report_path.name}",
        f"Files included: {result.files}",
        f"Folders counted: {result.directories}",
        f"Total size: {human_bytes(result.total_bytes)}",
        f"Items skipped: {result.filtered}",
        f"Verification hash: {hash_algorithm_label(result.hash_algorithm)}",
        f"First file in CSV: {result.first_csv_item or 'none'}",
        f"Last file in CSV: {result.last_csv_item or 'none'}",
        f"Finished in: {result.elapsed:.2f}s",
        "",
        *render_top("Top extensions by file count", result.top_by_count),
        "",
        *render_top("Top extensions by total size", result.top_by_size, by_size=True),
    ]
    return "\n".join(lines) + "\n"


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
    matches: list[Path] = []
    scanned = 0
    for path in sorted(source_dir.rglob("*")):
        if not path.is_file():
            continue
        scanned += 1
        if progress_callback is not None:
            progress_callback(
                EmailCopyProgress(
                    phase="scanning",
                    scanned=scanned,
                    matched=len(matches),
                    copied=0,
                    total=0,
                    current_name=path.name,
                )
            )
        if path.suffix.lower() in EMAIL_EXTENSIONS:
            matches.append(path)
            if progress_callback is not None:
                progress_callback(
                    EmailCopyProgress(
                        phase="scanning",
                        scanned=scanned,
                        matched=len(matches),
                        copied=0,
                        total=0,
                        current_name=path.name,
                    )
                )
    if progress_callback is not None:
        progress_callback(
            EmailCopyProgress(
                phase="copying",
                scanned=scanned,
                matched=len(matches),
                copied=0,
                total=len(matches),
            )
        )
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
                        scanned=scanned,
                        matched=len(matches),
                        copied=copied,
                        total=len(matches),
                        current_relative=relative.as_posix(),
                        current_name=path.name,
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
        "Your file list is ready.",
        f"Selected folder: {result.source_name}",
        f"Saved file list: {result.output_path.name}",
        f"Excel copy: {result.xlsx_path.name if result.xlsx_path else 'not created'}",
        f"Summary report: {result.report_path.name}",
        f"Files included: {result.files}",
        f"Folders counted: {result.directories}",
        f"Total size: {result.total_bytes} ({human_bytes(result.total_bytes)})",
        f"Items skipped: {result.filtered}",
        f"Hidden items skipped: {result.filtered_hidden}",
        f"System items skipped: {result.filtered_system}",
        f"Skipped by file type: {result.filtered_exts}",
        f"Verification hash: {hash_algorithm_label(result.hash_algorithm)}",
        f"First file in CSV: {result.first_csv_item or 'none'}",
        f"Last file in CSV: {result.last_csv_item or 'none'}",
        f"Excel copy enabled: {'on' if result.create_xlsx else 'off'}",
        f"Keep leading zeros in Excel: {'on' if result.preserve_zeros and result.create_xlsx else 'off'}",
        f"Finished in: {result.elapsed:.2f}s",
        "",
        *render_top("Most common file types", result.top_by_count),
        "",
        *render_top("Largest file types by size", result.top_by_size, by_size=True),
    ]
    return "\n".join(lines)
