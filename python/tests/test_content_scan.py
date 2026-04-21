from __future__ import annotations

import csv
import sys
import unittest
import zipfile
from pathlib import Path
from tempfile import TemporaryDirectory


CURRENT_DIR = Path(__file__).resolve().parent
PYTHON_DIR = CURRENT_DIR.parent
REPO_ROOT = PYTHON_DIR.parent
if str(PYTHON_DIR) not in sys.path:
    sys.path.insert(0, str(PYTHON_DIR))

import content_list_core as core


class ContentScanTests(unittest.TestCase):
    def test_run_scan_creates_xlsx_and_hashes(self) -> None:
        with TemporaryDirectory() as tmp:
            workspace = Path(tmp)
            source = workspace / "source"
            source.mkdir()
            (source / "0007.txt").write_text("hello\n", encoding="utf-8")

            result = core.run_scan(
                source,
                workspace / "report.csv",
                hash_algorithm=core.HASH_ALGORITHM_BLAKE3,
                include_hidden=False,
                include_system=False,
                excluded_exts=set(),
                create_xlsx=True,
                preserve_zeros=True,
                delete_csv=False,
            )

            self.assertEqual(result.files, 1)
            self.assertTrue(result.xlsx_path and result.xlsx_path.exists())
            self.assertTrue(result.report_path.exists())

            with (workspace / "report.csv").open("r", newline="", encoding="utf-8") as handle:
                rows = list(csv.reader(handle))
            self.assertEqual(rows[1][0], "0007.txt")
            self.assertEqual(rows[1][5], "BLAKE3")
            self.assertTrue(rows[1][6])
            report_text = result.report_path.read_text(encoding="utf-8")
            self.assertIn("Selected folder: source", report_text)
            self.assertIn("First file in CSV: 0007.txt", report_text)

    def test_convert_csv_to_xlsx_preserves_leading_zeros(self) -> None:
        with TemporaryDirectory() as tmp:
            workspace = Path(tmp)
            csv_path = workspace / "input.csv"
            csv_path.write_text(
                "File Name,Extension,Size in Bytes,Size in Human Readable,Path From Root Folder,Hash Algorithm,Hash Value\n"
                "sample.txt,txt,00123,123 B,nested/sample.txt,,\n",
                encoding="utf-8",
            )
            xlsx_path = workspace / "output.xlsx"

            core.convert_csv_to_xlsx(csv_path, xlsx_path, preserve_zeros=True)

            with zipfile.ZipFile(xlsx_path, "r") as archive:
                sheet_xml = archive.read("xl/worksheets/sheet1.xml").decode("utf-8")
            self.assertIn("00123", sheet_xml)

    def test_run_scan_matches_golden_fixture(self) -> None:
        source = REPO_ROOT / "testing" / "content-scan" / "fixtures" / "source"
        expected_path = REPO_ROOT / "testing" / "content-scan" / "fixtures" / "expected-scan-hash.csv"

        with TemporaryDirectory() as tmp:
            output_path = Path(tmp) / "report.csv"
            result = core.run_scan(
                source,
                output_path,
                hash_algorithm=core.HASH_ALGORITHM_SHA256,
                include_hidden=False,
                include_system=False,
                excluded_exts={"log"},
                create_xlsx=False,
                preserve_zeros=False,
                delete_csv=False,
            )

            self.assertEqual(result.files, 5)
            self.assertEqual(result.filtered, 3)
            self.assertEqual(output_path.read_text(encoding="utf-8"), expected_path.read_text(encoding="utf-8"))

    def test_run_scan_deletes_csv_after_xlsx_when_enabled(self) -> None:
        with TemporaryDirectory() as tmp:
            workspace = Path(tmp)
            source = workspace / "source"
            source.mkdir()
            (source / "keep.txt").write_text("hello\n", encoding="utf-8")
            output_path = workspace / "report.csv"

            result = core.run_scan(
                source,
                output_path,
                hash_algorithm=core.HASH_ALGORITHM_OFF,
                include_hidden=False,
                include_system=False,
                excluded_exts=set(),
                create_xlsx=True,
                preserve_zeros=True,
                delete_csv=True,
            )

            self.assertTrue(result.xlsx_path and result.xlsx_path.exists())
            self.assertTrue(result.csv_deleted)
            self.assertFalse(output_path.exists())


if __name__ == "__main__":
    unittest.main()
