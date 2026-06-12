from __future__ import annotations

import csv
import json
import sys
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory


CURRENT_DIR = Path(__file__).resolve().parent
PYTHON_DIR = CURRENT_DIR.parent
REPO_ROOT = PYTHON_DIR.parent
if str(PYTHON_DIR) not in sys.path:
    sys.path.insert(0, str(PYTHON_DIR))

import content_list_core as core


class EmailCopyTests(unittest.TestCase):
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

    def test_copy_email_matches_golden_fixture(self) -> None:
        source = REPO_ROOT / "testing" / "email-copy" / "fixtures" / "source"
        expected = json.loads(
            (REPO_ROOT / "testing" / "email-copy" / "fixtures" / "expected-email-manifest.json").read_text(encoding="utf-8")
        )

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
