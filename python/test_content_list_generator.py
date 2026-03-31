from __future__ import annotations

import csv
import sys
import unittest
import zipfile
from pathlib import Path
from tempfile import TemporaryDirectory


CURRENT_DIR = Path(__file__).resolve().parent
if str(CURRENT_DIR) not in sys.path:
    sys.path.insert(0, str(CURRENT_DIR))

import content_list_generator as clg


class ContentListGeneratorTests(unittest.TestCase):
    def test_run_scan_creates_xlsx_and_hashes(self) -> None:
        with TemporaryDirectory() as tmp:
            workspace = Path(tmp)
            source = workspace / "source"
            source.mkdir()
            (source / "0007.txt").write_text("hello\n", encoding="utf-8")

            result = clg.run_scan(
                source,
                workspace / "report.csv",
                hashing=True,
                include_hidden=False,
                include_system=False,
                excluded_exts=set(),
                create_xlsx=True,
                preserve_zeros=True,
            )

            self.assertEqual(result.files, 1)
            self.assertTrue(result.xlsx_path and result.xlsx_path.exists())

            with (workspace / "report.csv").open("r", newline="", encoding="utf-8") as handle:
                rows = list(csv.reader(handle))
            self.assertEqual(rows[1][0], "0007.txt")
            self.assertTrue(rows[1][5])

    def test_convert_csv_to_xlsx_preserves_leading_zeros(self) -> None:
        with TemporaryDirectory() as tmp:
            workspace = Path(tmp)
            csv_path = workspace / "input.csv"
            csv_path.write_text(
                "File Name,Extension,Size in Bytes,Size in Human Readable,Path From Root Folder,SHA256 Hash\n"
                "sample.txt,txt,00123,123 B,nested/sample.txt,\n",
                encoding="utf-8",
            )
            xlsx_path = workspace / "output.xlsx"

            clg.convert_csv_to_xlsx(csv_path, xlsx_path, preserve_zeros=True)

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

            result = clg.copy_email_files(source, dest)

            self.assertEqual(result.copied, 2)
            self.assertTrue((dest / "Inbox" / "mail.eml").exists())
            self.assertTrue((dest / "Inbox" / "nested" / "archive.pst").exists())
            self.assertTrue(result.manifest_path.exists())

            with result.manifest_path.open("r", newline="", encoding="utf-8") as handle:
                rows = list(csv.reader(handle))
            self.assertEqual(rows[0], clg.EMAIL_MANIFEST_HEADERS)
            self.assertEqual(rows[1][2], "Inbox/mail.eml")
            self.assertEqual(rows[2][4], ".pst")


if __name__ == "__main__":
    unittest.main()
