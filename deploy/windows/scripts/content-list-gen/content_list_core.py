from __future__ import annotations

import csv
import hashlib
import os
import shutil
import time
import zipfile
from collections import deque
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
DEFAULT_MAX_ROWS_PER_CSV = 300_000
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
CLONE_DIFF_HEADERS = [
    "Difference Type",
    "Path From Root Folder",
    "1st Drive File Name",
    "2nd Drive File Name",
    "1st Drive Size in Bytes",
    "2nd Drive Size in Bytes",
    "1st Drive Hash Algorithm",
    "2nd Drive Hash Algorithm",
    "1st Drive Hash Value",
    "2nd Drive Hash Value",
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
    output_paths: list[Path]
    xlsx_path: Path | None
    xlsx_paths: list[Path]
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
    delete_csv: bool
    csv_deleted: bool
    max_rows_per_csv: int
    csv_parts: int
    xlsx_parts: int
    hash_workers: int
    top_by_count: list[SummaryEntry]
    top_by_size: list[SummaryEntry]
    first_csv_item: str
    last_csv_item: str


@dataclass
class CloneCompareProgress:
    compared: int
    total: int
    differences: int
    current_name: str = ""


@dataclass
class CloneVerificationResult:
    drive_a: ScanResult
    drive_b: ScanResult
    diff_path: Path
    report_path: Path
    hash_algorithm: str
    elapsed: float
    compared: int
    differences: int
    missing_from_drive_b: int
    extra_on_drive_b: int
    size_mismatches: int
    hash_mismatches: int


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


@dataclass
class ScanCSVRow:
    file_name: str
    extension: str
    size: int
    relative_path: str
    hash_algorithm: str
    hash_value: str


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
    return HASH_ALGORITHM_SHA1


def is_blake3_available() -> bool:
    return blake3 is not None


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


def count_scan_targets(
    source_dir: Path,
    include_hidden: bool,
    include_system: bool,
    excluded_exts: set[str],
    progress_callback: Callable[[ScanProgress], None] | None = None,
    cancel_event=None,
) -> tuple[int, int, int, int, int, int, int]:
    files = 0
    filtered = 0
    filtered_hidden = 0
    filtered_system = 0
    filtered_exts = 0
    directories = 0
    total_bytes = 0

    for root, dirs, names in os.walk(source_dir):
        if cancel_event is not None and cancel_event.is_set():
            raise ScanCanceled()
        root_path = Path(root)
        directories += 1

        kept_dirs: list[str] = []
        for directory in dirs:
            candidate = root_path / directory
            if not include_hidden and is_hidden_path(candidate, source_dir):
                filtered += 1
                filtered_hidden += 1
                continue
            kept_dirs.append(directory)
        dirs[:] = sorted(kept_dirs)

        if progress_callback is not None and directories % 100 == 0:
            progress_callback(
                ScanProgress(
                    phase="counting",
                    files=files,
                    total_files=0,
                    directories=directories,
                    total_directories=0,
                    bytes=total_bytes,
                    total_bytes=0,
                    filtered=filtered,
                    current_name=root_path.name,
                )
            )

        for file_name in sorted(names):
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
            try:
                stat = candidate.stat()
            except OSError:
                continue
            if not candidate.is_file():
                continue
            files += 1
            total_bytes += stat.st_size
            if progress_callback is not None and files % 250 == 0:
                progress_callback(
                    ScanProgress(
                        phase="counting",
                        files=files,
                        total_files=0,
                        directories=directories,
                        total_directories=0,
                        bytes=total_bytes,
                        total_bytes=0,
                        filtered=filtered,
                        current_name=file_name,
                    )
                )

    if progress_callback is not None:
        progress_callback(
            ScanProgress(
                phase="counting",
                files=files,
                total_files=0,
                directories=directories,
                total_directories=0,
                bytes=total_bytes,
                total_bytes=0,
                filtered=filtered,
            )
        )
    return files, filtered, filtered_hidden, filtered_system, filtered_exts, directories, total_bytes


def iter_scan_files(
    source_dir: Path,
    include_hidden: bool,
    include_system: bool,
    excluded_exts: set[str],
    cancel_event=None,
):
    for root, dirs, names in os.walk(source_dir):
        if cancel_event is not None and cancel_event.is_set():
            raise ScanCanceled()
        root_path = Path(root)

        kept_dirs: list[str] = []
        for directory in dirs:
            candidate = root_path / directory
            if not include_hidden and is_hidden_path(candidate, source_dir):
                continue
            kept_dirs.append(directory)
        dirs[:] = sorted(kept_dirs)

        for file_name in sorted(names):
            if cancel_event is not None and cancel_event.is_set():
                raise ScanCanceled()
            candidate = root_path / file_name
            _, skipped = should_skip(candidate, source_dir, include_hidden, include_system, excluded_exts)
            if skipped:
                continue
            try:
                stat = candidate.stat()
            except OSError:
                continue
            if not candidate.is_file():
                continue
            yield candidate, stat.st_size, candidate.relative_to(source_dir).as_posix()


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


def csv_output_path_for_part(output_path: Path, part_number: int) -> Path:
    part_number = max(1, int(part_number))
    stem = output_path.stem
    suffix = output_path.suffix or ".csv"
    return output_path.with_name(f"{stem}-{part_number:03d}{suffix}")


def clone_output_path_for_drive_b(output_path: Path) -> Path:
    return output_path.with_name(f"{output_path.stem}-clone-b{output_path.suffix or '.csv'}")


def clone_diff_csv_path(output_path: Path) -> Path:
    return output_path.with_name(f"{output_path.stem}-clone-differences{output_path.suffix or '.csv'}")


def clone_diff_report_path(output_path: Path) -> Path:
    return output_path.with_name(f"{output_path.stem}-clone-report.txt")


def compare_progress_fraction(progress: CloneCompareProgress) -> float:
    if progress.total <= 0:
        return 0.0
    value = progress.compared / max(1, progress.total)
    return max(0.0, min(1.0, value))


def iter_scan_csv_rows(paths: list[Path]):
    for path in paths:
        with path.open("r", newline="", encoding="utf-8") as handle:
            reader = csv.reader(handle)
            next(reader, None)
            for row in reader:
                if len(row) < 7:
                    raise RuntimeError(f"Scan CSV row in {path} is missing columns")
                try:
                    size = int(str(row[2]).strip())
                except ValueError as exc:
                    raise RuntimeError(f"Scan CSV row in {path} has invalid size: {row[2]!r}") from exc
                yield ScanCSVRow(
                    file_name=row[0],
                    extension=row[1],
                    size=size,
                    relative_path=row[4],
                    hash_algorithm=row[5],
                    hash_value=row[6],
                )


class ChunkedCSVReportWriter:
    def __init__(self, output_path: Path, max_rows_per_csv: int) -> None:
        self.output_path = output_path
        self.max_rows_per_csv = max(1, max_rows_per_csv)
        self.part_paths: list[Path] = []
        self._part_number = 0
        self._rows_in_part = 0
        self._handle = None
        self._writer = None
        self._open_next_part()

    def _path_for_part(self, part_number: int) -> Path:
        return csv_output_path_for_part(self.output_path, part_number)

    def _open_next_part(self) -> None:
        self.close()
        self._part_number += 1
        part_path = self._path_for_part(self._part_number)
        part_path.parent.mkdir(parents=True, exist_ok=True)
        self._handle = part_path.open("w", newline="", encoding="utf-8")
        self._writer = csv.writer(self._handle)
        self._writer.writerow(REPORT_HEADERS)
        self._rows_in_part = 0
        self.part_paths.append(part_path)

    def write_row(self, row: list[str]) -> None:
        if self._writer is None:
            raise RuntimeError("CSV writer is not initialized")
        if self._rows_in_part >= self.max_rows_per_csv:
            self._open_next_part()
        self._writer.writerow(row)
        self._rows_in_part += 1

    def close(self) -> None:
        if self._handle is not None:
            self._handle.close()
            self._handle = None
            self._writer = None


def write_csv_report(
    source_dir: Path,
    output_path: Path,
    *,
    hash_algorithm: str,
    include_hidden: bool,
    include_system: bool,
    excluded_exts: set[str],
    max_rows_per_csv: int,
    total_expected_files: int,
    total_directories: int,
    filtered: int,
    total_expected_bytes: int,
    progress_callback: Callable[[ScanProgress], None] | None = None,
    cancel_event=None,
) -> tuple[int, int, dict[str, dict[str, int]], int, str, str, list[Path]]:
    summaries: dict[str, dict[str, int]] = {}
    processed_bytes = 0
    processed_files = 0
    first_csv_item = ""
    last_csv_item = ""
    hash_workers = 1
    normalized_algorithm = normalize_hash_algorithm(hash_algorithm)
    csv_writer = ChunkedCSVReportWriter(output_path, max_rows_per_csv)

    def write_processed_row(file_path: Path, size: int, relative: str, file_hash: str) -> None:
        nonlocal processed_bytes, processed_files, first_csv_item, last_csv_item
        ext = normalize_extension(file_path)
        bucket = summaries.setdefault(summary_key(ext), {"count": 0, "bytes": 0})
        bucket["count"] += 1
        bucket["bytes"] += size
        csv_writer.write_row(
            [
                file_path.name,
                ext,
                str(size),
                human_bytes(size),
                relative,
                hash_algorithm_csv_name(normalized_algorithm),
                file_hash,
            ]
        )
        processed_files += 1
        processed_bytes += size
        if not first_csv_item:
            first_csv_item = relative
        last_csv_item = relative
        if progress_callback is not None:
            progress_callback(
                ScanProgress(
                    phase="scanning",
                    files=processed_files,
                    total_files=total_expected_files,
                    directories=total_directories,
                    total_directories=total_directories,
                    bytes=processed_bytes,
                    total_bytes=total_expected_bytes,
                    filtered=filtered,
                    current_name=file_path.name,
                )
            )

    try:
        if normalized_algorithm != HASH_ALGORITHM_OFF:
            hash_workers = max(2, os.cpu_count() or 2)
            max_in_flight = max(hash_workers*4, 8)
            with ThreadPoolExecutor(max_workers=hash_workers) as pool:
                pending = deque()
                for file_path, size, relative in iter_scan_files(
                    source_dir,
                    include_hidden,
                    include_system,
                    excluded_exts,
                    cancel_event=cancel_event,
                ):
                    if cancel_event is not None and cancel_event.is_set():
                        raise ScanCanceled()
                    pending.append(
                        (
                            file_path,
                            size,
                            relative,
                            pool.submit(hash_file, file_path, normalized_algorithm, cancel_event),
                        )
                    )
                    if len(pending) >= max_in_flight:
                        next_path, next_size, next_relative, next_future = pending.popleft()
                        write_processed_row(next_path, next_size, next_relative, next_future.result())

                while pending:
                    next_path, next_size, next_relative, next_future = pending.popleft()
                    write_processed_row(next_path, next_size, next_relative, next_future.result())
        else:
            for file_path, size, relative in iter_scan_files(
                source_dir,
                include_hidden,
                include_system,
                excluded_exts,
                cancel_event=cancel_event,
            ):
                if cancel_event is not None and cancel_event.is_set():
                    raise ScanCanceled()
                write_processed_row(file_path, size, relative, "")
    finally:
        csv_writer.close()

    return processed_files, processed_bytes, summaries, hash_workers, first_csv_item, last_csv_item, csv_writer.part_paths


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


def convert_csv_to_xlsx(csv_path: Path, xlsx_path: Path, preserve_zeros: bool) -> None:
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
        with csv_path.open("r", newline="", encoding="utf-8") as handle:
            reader = csv.reader(handle)
            with archive.open("xl/worksheets/sheet1.xml", "w") as sheet:
                sheet.write(
                    (
                        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
                        '<worksheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main" '
                        'xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships">'
                        '<sheetViews><sheetView workbookViewId="0"/></sheetViews>'
                        '<sheetFormatPr defaultRowHeight="15"/>'
                        "<sheetData>"
                    ).encode("utf-8")
                )
                for row_index, row in enumerate(reader, start=1):
                    cells: list[str] = []
                    for col_index, value in enumerate(row, start=1):
                        ref = _xlsx_cell_ref(row_index, col_index)
                        if preserve_zeros:
                            cells.append(_xlsx_inline_cell(ref, value, style_id=1))
                        elif row_index > 1 and col_index == 3 and value.isdigit():
                            cells.append(_xlsx_number_cell(ref, value))
                        else:
                            cells.append(_xlsx_inline_cell(ref, value))
                    row_xml = f'<row r="{row_index}">{"".join(cells)}</row>'
                    sheet.write(row_xml.encode("utf-8"))
                sheet.write(b"</sheetData></worksheet>")


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
    delete_csv: bool,
    max_rows_per_csv: int = DEFAULT_MAX_ROWS_PER_CSV,
    progress_callback: Callable[[ScanProgress], None] | None = None,
    cancel_event=None,
) -> ScanResult:
    started = time.time()
    max_rows_per_csv = max(1, int(max_rows_per_csv or DEFAULT_MAX_ROWS_PER_CSV))
    csv_paths: list[Path] = []
    xlsx_paths: list[Path] = []
    xlsx_path: Path | None = None
    csv_deleted = False
    report_path = output_path.with_name(f"{output_path.stem}-report.txt")
    try:
        total_files, filtered, filtered_hidden, filtered_system, filtered_exts, directories, total_expected_bytes = count_scan_targets(
            source_dir,
            include_hidden,
            include_system,
            excluded_exts,
            progress_callback=progress_callback,
            cancel_event=cancel_event,
        )
        file_count, total_bytes, summaries, hash_workers, first_csv_item, last_csv_item, csv_paths = write_csv_report(
            source_dir,
            output_path,
            hash_algorithm=hash_algorithm,
            include_hidden=include_hidden,
            include_system=include_system,
            excluded_exts=excluded_exts,
            max_rows_per_csv=max_rows_per_csv,
            total_expected_files=total_files,
            total_directories=directories,
            filtered=filtered,
            total_expected_bytes=total_expected_bytes,
            progress_callback=progress_callback,
            cancel_event=cancel_event,
        )
        if create_xlsx:
            for csv_part_path in csv_paths:
                if cancel_event is not None and cancel_event.is_set():
                    raise ScanCanceled()
                xlsx_part_path = csv_part_path.with_suffix(".xlsx")
                convert_csv_to_xlsx(csv_part_path, xlsx_part_path, preserve_zeros)
                xlsx_paths.append(xlsx_part_path)
            if xlsx_paths:
                xlsx_path = xlsx_paths[0]
            if delete_csv:
                for csv_part_path in csv_paths:
                    csv_part_path.unlink(missing_ok=True)
                csv_deleted = True
        result = ScanResult(
            source_name=folder_display_name(source_dir),
            output_path=csv_paths[0] if csv_paths else output_path,
            output_paths=csv_paths or [output_path],
            xlsx_path=xlsx_path,
            xlsx_paths=xlsx_paths,
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
            delete_csv=delete_csv,
            csv_deleted=csv_deleted,
            max_rows_per_csv=max_rows_per_csv,
            csv_parts=len(csv_paths or [output_path]),
            xlsx_parts=len(xlsx_paths),
            hash_workers=hash_workers,
            top_by_count=summarize_entries(summaries, "count"),
            top_by_size=summarize_entries(summaries, "bytes"),
            first_csv_item=first_csv_item,
            last_csv_item=last_csv_item,
        )
        write_scan_report(result)
        return result
    except ScanCanceled:
        cleanup_paths = list(csv_paths)
        cleanup_paths.extend(xlsx_paths)
        cleanup_paths.extend(
            [
                output_path,
                output_path.with_suffix(".xlsx"),
                report_path,
            ]
        )
        for path in cleanup_paths:
            try:
                path.unlink()
            except FileNotFoundError:
                pass
        raise


def write_scan_report(result: ScanResult) -> None:
    result.report_path.write_text(build_scan_report(result), encoding="utf-8")


def summarize_output_parts(paths: list[Path]) -> str:
    if not paths:
        return "none"
    max_shown = 4
    labels = [path.name for path in paths[:max_shown]]
    if len(paths) > max_shown:
        return f"{', '.join(labels)} (+{len(paths) - max_shown} more)"
    return ", ".join(labels)


def build_scan_report(result: ScanResult) -> str:
    lines = [
        "Content List Report",
        f"Selected folder: {result.source_name}",
        f"Saved file list: {result.output_path.name}",
        f"CSV files created: {result.csv_parts}",
        f"Rows per CSV max: {result.max_rows_per_csv}",
        f"CSV parts: {summarize_output_parts(result.output_paths)}",
        f"Excel copy: {result.xlsx_path.name if result.xlsx_path else 'not created'}",
        f"XLSX files created: {result.xlsx_parts}",
        f"XLSX parts: {summarize_output_parts(result.xlsx_paths)}",
        f"Summary report: {result.report_path.name}",
        f"Files included: {result.files}",
        f"Folders counted: {result.directories}",
        f"Total size: {human_bytes(result.total_bytes)}",
        f"Items skipped: {result.filtered}",
        f"Verification hash: {hash_algorithm_label(result.hash_algorithm)}",
        f"First file in CSV: {result.first_csv_item or 'none'}",
        f"Last file in CSV: {result.last_csv_item or 'none'}",
        f"Delete CSV after XLSX: {'on' if result.delete_csv and result.create_xlsx else 'off'}",
        f"CSV removed after XLSX: {'on' if result.csv_deleted else 'off'}",
        f"Finished in: {result.elapsed:.2f}s",
        "",
        *render_top("Top extensions by file count", result.top_by_count),
        "",
        *render_top("Top extensions by total size", result.top_by_size, by_size=True),
    ]
    return "\n".join(lines) + "\n"


def compare_scan_outputs(
    drive_a: ScanResult,
    drive_b: ScanResult,
    diff_path: Path,
    report_path: Path,
    progress_callback: Callable[[CloneCompareProgress], None] | None = None,
    cancel_event=None,
) -> CloneVerificationResult:
    started = time.time()
    compared = 0
    differences = 0
    missing_from_drive_b = 0
    extra_on_drive_b = 0
    size_mismatches = 0
    hash_mismatches = 0
    diff_path.parent.mkdir(parents=True, exist_ok=True)

    iterator_a = iter_scan_csv_rows(drive_a.output_paths)
    iterator_b = iter_scan_csv_rows(drive_b.output_paths)

    def safe_next(iterator):
        try:
            return next(iterator)
        except StopIteration:
            return None

    def send_progress(current_name: str) -> None:
        if progress_callback is None:
            return
        progress_callback(
            CloneCompareProgress(
                compared=compared,
                total=max(drive_a.files, drive_b.files),
                differences=differences,
                current_name=current_name,
            )
        )

    next_a = safe_next(iterator_a)
    next_b = safe_next(iterator_b)

    try:
        with diff_path.open("w", newline="", encoding="utf-8") as handle:
            writer = csv.writer(handle)
            writer.writerow(CLONE_DIFF_HEADERS)

            while next_a is not None or next_b is not None:
                if cancel_event is not None and cancel_event.is_set():
                    raise ScanCanceled()

                if next_a is not None and next_b is not None and next_a.relative_path == next_b.relative_path:
                    compared += 1
                    size_mismatch = next_a.size != next_b.size
                    hash_mismatch = (
                        next_a.hash_value != next_b.hash_value
                        or next_a.hash_algorithm != next_b.hash_algorithm
                    )
                    diff_type = ""
                    if size_mismatch and hash_mismatch:
                        diff_type = "size and hash mismatch"
                        size_mismatches += 1
                        hash_mismatches += 1
                    elif size_mismatch:
                        diff_type = "size mismatch"
                        size_mismatches += 1
                    elif hash_mismatch:
                        diff_type = "hash mismatch"
                        hash_mismatches += 1
                    if diff_type:
                        differences += 1
                        writer.writerow(
                            [
                                diff_type,
                                next_a.relative_path,
                                next_a.file_name,
                                next_b.file_name,
                                str(next_a.size),
                                str(next_b.size),
                                next_a.hash_algorithm,
                                next_b.hash_algorithm,
                                next_a.hash_value,
                                next_b.hash_value,
                            ]
                        )
                    send_progress(next_a.relative_path)
                    next_a = safe_next(iterator_a)
                    next_b = safe_next(iterator_b)
                    continue

                if next_b is None or (next_a is not None and next_a.relative_path < next_b.relative_path):
                    differences += 1
                    missing_from_drive_b += 1
                    writer.writerow(
                        [
                            "missing from 2nd Drive",
                            next_a.relative_path,
                            next_a.file_name,
                            "",
                            str(next_a.size),
                            "",
                            next_a.hash_algorithm,
                            "",
                            next_a.hash_value,
                            "",
                        ]
                    )
                    send_progress(next_a.relative_path)
                    next_a = safe_next(iterator_a)
                    continue

                differences += 1
                extra_on_drive_b += 1
                writer.writerow(
                    [
                        "extra on 2nd Drive",
                        next_b.relative_path,
                        "",
                        next_b.file_name,
                        "",
                        str(next_b.size),
                        "",
                        next_b.hash_algorithm,
                        "",
                        next_b.hash_value,
                    ]
                )
                send_progress(next_b.relative_path)
                next_b = safe_next(iterator_b)
    except Exception:
        diff_path.unlink(missing_ok=True)
        report_path.unlink(missing_ok=True)
        raise

    result = CloneVerificationResult(
        drive_a=drive_a,
        drive_b=drive_b,
        diff_path=diff_path,
        report_path=report_path,
        hash_algorithm=normalize_hash_algorithm(drive_a.hash_algorithm),
        elapsed=time.time() - started,
        compared=compared,
        differences=differences,
        missing_from_drive_b=missing_from_drive_b,
        extra_on_drive_b=extra_on_drive_b,
        size_mismatches=size_mismatches,
        hash_mismatches=hash_mismatches,
    )
    write_clone_verification_report(result)
    return result


def write_clone_verification_report(result: CloneVerificationResult) -> None:
    result.report_path.write_text(build_clone_verification_report(result), encoding="utf-8")


def build_clone_verification_report(result: CloneVerificationResult) -> str:
    status = "match" if result.differences == 0 else "differences found"
    lines = [
        "Clone Verification Report",
        f"Verification result: {status}",
        f"1st Drive folder: {result.drive_a.source_name}",
        f"2nd Drive folder: {result.drive_b.source_name}",
        f"1st Drive content list: {result.drive_a.output_path.name}",
        f"2nd Drive content list: {result.drive_b.output_path.name}",
        f"1st Drive summary report: {result.drive_a.report_path.name}",
        f"2nd Drive summary report: {result.drive_b.report_path.name}",
        f"Differences CSV: {result.diff_path.name}",
        f"Verification hash: {hash_algorithm_label(result.hash_algorithm)}",
        f"Matched paths checked: {result.compared}",
        f"Missing from 2nd Drive: {result.missing_from_drive_b}",
        f"Extra on 2nd Drive: {result.extra_on_drive_b}",
        f"Size mismatches: {result.size_mismatches}",
        f"Hash mismatches: {result.hash_mismatches}",
        f"Total differences: {result.differences}",
        f"Finished in: {result.elapsed:.2f}s",
    ]
    return "\n".join(lines) + "\n"


def build_clone_verification_summary(result: CloneVerificationResult) -> str:
    status = "Clone verification passed." if result.differences == 0 else "Clone verification found differences."
    lines = [
        status,
        f"1st Drive folder: {result.drive_a.source_name}",
        f"2nd Drive folder: {result.drive_b.source_name}",
        f"1st Drive content list: {result.drive_a.output_path.name}",
        f"2nd Drive content list: {result.drive_b.output_path.name}",
        f"Differences CSV: {result.diff_path.name}",
        f"Clone report: {result.report_path.name}",
        f"Verification hash: {hash_algorithm_label(result.hash_algorithm)}",
        f"Missing from 2nd Drive: {result.missing_from_drive_b}",
        f"Extra on 2nd Drive: {result.extra_on_drive_b}",
        f"Size mismatches: {result.size_mismatches}",
        f"Hash mismatches: {result.hash_mismatches}",
        f"Total differences: {result.differences}",
        f"Finished in: {result.elapsed:.2f}s",
    ]
    return "\n".join(lines)


def delete_deferred_scan_csvs(result: ScanResult, delete_requested: bool) -> None:
    result.delete_csv = delete_requested
    if not delete_requested or not result.create_xlsx:
        return
    for csv_path in result.output_paths:
        csv_path.unlink(missing_ok=True)
    result.csv_deleted = True
    write_scan_report(result)


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
        f"CSV files created: {result.csv_parts}",
        f"Rows per CSV max: {result.max_rows_per_csv}",
        f"CSV parts: {summarize_output_parts(result.output_paths)}",
        f"Excel copy: {result.xlsx_path.name if result.xlsx_path else 'not created'}",
        f"XLSX files created: {result.xlsx_parts}",
        f"XLSX parts: {summarize_output_parts(result.xlsx_paths)}",
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
        f"Delete CSV after XLSX: {'on' if result.delete_csv and result.create_xlsx else 'off'}",
        f"CSV removed after XLSX: {'on' if result.csv_deleted else 'off'}",
        f"Finished in: {result.elapsed:.2f}s",
        "",
        *render_top("Most common file types", result.top_by_count),
        "",
        *render_top("Largest file types by size", result.top_by_size, by_size=True),
    ]
    return "\n".join(lines)
