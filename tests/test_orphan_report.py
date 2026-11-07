"""Conservative read-only orphan reporting and age/reference protections."""

import os
from contextlib import closing
from pathlib import Path
import sqlite3
import tempfile
import time
import unittest

from zhiwiki.service.orphan_report import orphan_report


class OrphanReportTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.uploads = self.root / "uploads"
        self.uploads.mkdir()
        self.db = self.root / "knowledge.sqlite3"
        with closing(sqlite3.connect(str(self.db))) as connection:
            connection.execute("CREATE TABLE team_revisions(file_hash TEXT)")
            connection.commit()

    def tearDown(self):
        self.temp.cleanup()

    def test_report_only_includes_old_unreferenced_regular_blobs(self):
        old, referenced, recent = "a" * 64, "b" * 64, "c" * 64
        for name in (old, referenced, recent, "upload_example.pending"):
            (self.uploads / name).write_text("test", encoding="utf-8")
        old_time = time.time() - 90000
        for name in (old, referenced):
            os.utime(self.uploads / name, (old_time, old_time))
        with closing(sqlite3.connect(str(self.db))) as connection:
            connection.execute("INSERT INTO team_revisions VALUES(?)", (referenced,))
            connection.commit()
        report = orphan_report(str(self.root))
        self.assertEqual([item["hash"] for item in report["candidates"]], [old])
        self.assertEqual(report["candidate_bytes"], 4)
        self.assertTrue(all((self.uploads / name).exists() for name in (old, referenced, recent)))
        self.assertEqual(report["mode"], "report_only")

    def test_invalid_or_missing_workspace_fails_without_creating_files(self):
        with self.assertRaises(ValueError):
            orphan_report(str(self.root), grace_seconds=1)
        absent = self.root / "absent"
        with self.assertRaises(ValueError):
            orphan_report(str(absent))
        self.assertFalse(absent.exists())


if __name__ == "__main__":
    unittest.main()
