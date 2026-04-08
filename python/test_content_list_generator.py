from __future__ import annotations

import csv
import json
import sys
import unittest
import zipfile
from pathlib import Path
from tempfile import TemporaryDirectory


CURRENT_DIR = Path(__file__).resolve().parent
if str(CURRENT_DIR) not in sys.path:
    sys.path.insert(0, str(CURRENT_DIR))

import content_list_core as core


class ContentListGeneratorTests(unittest.TestCase):
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

    def test_copy_email_files_preserves_structure_and_manifest(self) -> None:
        with TemporaryDirectory() as tmp:
            workspace = Path(tmp)
            source = workspace / "source"
            dest = workspace / "dest"
            (source / "Inbox" / "nested").mkdir(parents=True)
            (source / "Inbox" / "mail.eml").write_text("message", encoding="utf-8")
            (source / "Inbox" / "nested" / "archive.pst").write_text("archive", encoding="utf-8")
            (source / "Inbox" / "ignore.txt").write_text("ignore", encoding="utf-8")

            result = core.copy_email_files(source, dest)

            self.assertEqual(result.copied, 2)
            self.assertTrue((dest / "Inbox" / "mail.eml").exists())
            self.assertTrue((dest / "Inbox" / "nested" / "archive.pst").exists())
            self.assertTrue(result.manifest_path.exists())

            with result.manifest_path.open("r", newline="", encoding="utf-8") as handle:
                rows = list(csv.reader(handle))
            self.assertEqual(rows[0], core.EMAIL_MANIFEST_HEADERS)
            self.assertEqual(rows[1][2], "Inbox/mail.eml")
            self.assertEqual(rows[2][4], ".pst")

    def test_copy_email_files_rejects_nested_destination(self) -> None:
        with TemporaryDirectory() as tmp:
            workspace = Path(tmp)
            source = workspace / "source"
            source.mkdir()

            with self.assertRaisesRegex(ValueError, "inside the source folder"):
                core.copy_email_files(source, source / "copied-emails")

    def test_copy_email_files_includes_olk15message(self) -> None:
        with TemporaryDirectory() as tmp:
            workspace = Path(tmp)
            source = workspace / "source"
            dest = workspace / "dest"
            (source / "Inbox").mkdir(parents=True)
            (source / "Inbox" / "note.olk15Message").write_text("olk", encoding="utf-8")

            result = core.copy_email_files(source, dest)

            self.assertEqual(result.copied, 1)
            self.assertTrue((dest / "Inbox" / "note.olk15Message").exists())

    def test_run_scan_matches_golden_fixture(self) -> None:
        repo_root = CURRENT_DIR.parent
        source = repo_root / "testdata" / "parity" / "source"
        expected_path = repo_root / "testdata" / "parity" / "expected-scan-hash.csv"

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
            )

            self.assertEqual(result.files, 5)
            self.assertEqual(result.filtered, 3)
            self.assertEqual(output_path.read_text(encoding="utf-8"), expected_path.read_text(encoding="utf-8"))

    def test_copy_email_matches_golden_fixture(self) -> None:
        repo_root = CURRENT_DIR.parent
        source = repo_root / "testdata" / "parity" / "source"
        expected = json.loads((repo_root / "testdata" / "parity" / "expected-email-manifest.json").read_text(encoding="utf-8"))

        with TemporaryDirectory() as tmp:
            dest = Path(tmp) / "emails"
            result = core.copy_email_files(source, dest)

            self.assertEqual(result.copied, expected["copied"])

            with result.manifest_path.open("r", newline="", encoding="utf-8") as handle:
                rows = list(csv.DictReader(handle))
            normalized = [
                {
                    "Relative Path": row["Relative Path"],
                    "File Name": row["File Name"],
                    "Extension": row["Extension"],
                    "Size in Bytes": row["Size in Bytes"],
                }
                for row in rows
            ]
            self.assertEqual(normalized, expected["rows"])
            for row in normalized:
                self.assertTrue((dest / row["Relative Path"]).exists())


if __name__ == "__main__":
    unittest.main()
