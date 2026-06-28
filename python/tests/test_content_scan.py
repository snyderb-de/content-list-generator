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
            self.assertEqual(result.output_path.name, "report-001.csv")

            with result.output_path.open("r", newline="", encoding="utf-8") as handle:
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

    def test_run_scan_writes_agency_template(self) -> None:
        with TemporaryDirectory() as tmp:
            workspace = Path(tmp)
            source = workspace / "source"
            (source / "contracts").mkdir(parents=True)
            (source / "contracts" / "vendor.pdf").write_text("pdf bytes", encoding="utf-8")

            result = core.run_scan(
                source,
                workspace / "agency.csv",
                hash_algorithm=core.HASH_ALGORITHM_OFF,
                include_hidden=False,
                include_system=False,
                excluded_exts=set(),
                create_xlsx=False,
                preserve_zeros=False,
                delete_csv=False,
                agency_template=True,
                agency_fields={
                    "rg": "1325",
                    "sg": "1",
                    "series": "35",
                    "rc_series": "GAR-014",
                    "dept_organization": "Department of State",
                    "rc_series_name": "Annual Reports",
                    "begin_date": "2024",
                    "end_date": "2024",
                    "material_type": "Born Digital",
                    "confidential": "No",
                    "td_num": "3452",
                    "location_id": "Q: Drive",
                    "record_level": "Item",
                },
            )

            with result.output_path.open("r", newline="", encoding="utf-8") as handle:
                rows = list(csv.reader(handle))
            self.assertEqual(rows[0], core.AGENCY_TEMPLATE_HEADERS)
            self.assertEqual(rows[1][0], "1325")
            self.assertEqual(rows[1][1], "001")
            self.assertEqual(rows[1][2], "035")
            self.assertEqual(rows[1][4], "GAR-014")
            self.assertEqual(rows[1][13], "vendor.pdf")
            self.assertEqual(rows[1][15], "contracts")
            self.assertEqual(rows[1][22], "PDF")
            self.assertEqual(rows[1][28], "3452")
            self.assertEqual(rows[1][29], "Q: Drive")
            self.assertEqual(rows[1][30], "Item")

    def test_run_scan_rejects_invalid_agency_codes(self) -> None:
        with TemporaryDirectory() as tmp:
            workspace = Path(tmp)
            source = workspace / "source"
            source.mkdir()
            (source / "vendor.pdf").write_text("pdf bytes", encoding="utf-8")

            cases = [
                ({"rg": "12A4", "sg": "1", "series": "35"}, "RG must contain only digits"),
                ({"rg": "1325", "sg": "1234", "series": "35"}, "SG must be 3 digits or fewer"),
                ({"rg": "1325", "sg": "1", "series": "1234"}, "Series must be 3 digits or fewer"),
            ]
            for agency_fields, expected_error in cases:
                with self.subTest(expected_error=expected_error):
                    with self.assertRaisesRegex(ValueError, expected_error):
                        core.run_scan(
                            source,
                            workspace / "agency.csv",
                            hash_algorithm=core.HASH_ALGORITHM_OFF,
                            include_hidden=False,
                            include_system=False,
                            excluded_exts=set(),
                            create_xlsx=False,
                            preserve_zeros=False,
                            delete_csv=False,
                            agency_template=True,
                            agency_fields=agency_fields,
                        )

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
            with result.output_path.open("r", newline="", encoding="utf-8") as actual_handle:
                actual_rows = list(csv.reader(actual_handle))
            with expected_path.open("r", newline="", encoding="utf-8") as expected_handle:
                expected_rows = list(csv.reader(expected_handle))
            self.assertEqual(actual_rows, expected_rows)

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
            self.assertFalse(result.output_path.exists())

    def test_run_scan_splits_csv_and_converts_all_parts(self) -> None:
        with TemporaryDirectory() as tmp:
            workspace = Path(tmp)
            source = workspace / "source"
            source.mkdir()
            for index in range(5):
                (source / f"file-{index}.txt").write_text(f"value-{index}\n", encoding="utf-8")

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
                max_rows_per_csv=2,
            )

            self.assertEqual(result.csv_parts, 3)
            self.assertEqual(result.xlsx_parts, 3)
            self.assertEqual(len(result.output_paths), 3)
            self.assertEqual(len(result.xlsx_paths), 3)
            self.assertTrue(result.csv_deleted)
            for csv_part in result.output_paths:
                self.assertFalse(csv_part.exists())
            for xlsx_part in result.xlsx_paths:
                self.assertTrue(xlsx_part.exists())

    def test_compare_scan_outputs_reports_differences(self) -> None:
        with TemporaryDirectory() as tmp:
            workspace = Path(tmp)
            drive_a = workspace / "drive-a"
            drive_b = workspace / "drive-b"
            (drive_a / "nested").mkdir(parents=True)
            (drive_b / "nested").mkdir(parents=True)

            (drive_a / "match.txt").write_text("same", encoding="utf-8")
            (drive_b / "match.txt").write_text("same", encoding="utf-8")
            (drive_a / "missing.txt").write_text("only a", encoding="utf-8")
            (drive_b / "extra.txt").write_text("only b", encoding="utf-8")
            (drive_a / "nested" / "diff.txt").write_text("first", encoding="utf-8")
            (drive_b / "nested" / "diff.txt").write_text("second", encoding="utf-8")

            result_a = core.run_scan(
                drive_a,
                workspace / "drive-a.csv",
                hash_algorithm=core.HASH_ALGORITHM_SHA256,
                include_hidden=False,
                include_system=False,
                excluded_exts=set(),
                create_xlsx=False,
                preserve_zeros=False,
                delete_csv=False,
            )
            result_b = core.run_scan(
                drive_b,
                workspace / "drive-b.csv",
                hash_algorithm=core.HASH_ALGORITHM_SHA256,
                include_hidden=False,
                include_system=False,
                excluded_exts=set(),
                create_xlsx=False,
                preserve_zeros=False,
                delete_csv=False,
            )

            compare_result = core.compare_scan_outputs(
                result_a,
                result_b,
                workspace / "clone-diff.csv",
                workspace / "clone-report.txt",
            )

            self.assertEqual(compare_result.missing_no_match, 1)
            self.assertEqual(compare_result.extra_no_match, 1)
            self.assertEqual(compare_result.hash_mismatches, 1)
            self.assertEqual(compare_result.differences, 3)
            self.assertEqual(compare_result.verdict, core.CLONE_VERDICT_NOT)
            with compare_result.diff_path.open("r", newline="", encoding="utf-8") as handle:
                diff_rows = list(csv.reader(handle))
            self.assertEqual(len(diff_rows), 4)
            report_text = compare_result.report_path.read_text(encoding="utf-8")
            self.assertIn("Missing from 2nd Drive (no hash match): 1", report_text)

    def test_delete_deferred_scan_csvs_removes_files(self) -> None:
        with TemporaryDirectory() as tmp:
            workspace = Path(tmp)
            source = workspace / "source"
            source.mkdir()
            (source / "keep.txt").write_text("hello\n", encoding="utf-8")

            result = core.run_scan(
                source,
                workspace / "report.csv",
                hash_algorithm=core.HASH_ALGORITHM_OFF,
                include_hidden=False,
                include_system=False,
                excluded_exts=set(),
                create_xlsx=True,
                preserve_zeros=True,
                delete_csv=False,
            )

            core.delete_deferred_scan_csvs(result, True)

            self.assertTrue(result.csv_deleted)
            for csv_part in result.output_paths:
                self.assertFalse(csv_part.exists())


if __name__ == "__main__":
    unittest.main()
