"""Preflight tests use temporary JSON and never inspect environment files."""

import json
import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from zhiwiki.service.preflight import main, run_preflight


class PreflightTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.data = self.root / "data"
        self.backup = self.root / "backup"
        self.data.mkdir()
        self.backup.mkdir()
        self.config = self.root / "config.json"

    def tearDown(self):
        self.temp.cleanup()

    def write_config(self, **overrides):
        config = {"data_dir": str(self.data), "worker_python": sys.executable,
                  "allowed_hosts": ["localhost", "rag.internal.company"], "cookie_secure": True}
        config.update(overrides)
        self.config.write_text(json.dumps(config), encoding="utf-8")

    def test_missing_backup_blocks_and_unknowns_are_not_readiness(self):
        self.write_config()
        report = run_preflight(self.config)
        checks = {item["code"]: item["status"] for item in report["checks"]}
        self.assertEqual(checks["backup_directory"], "fail")
        self.assertEqual(checks["tls_proxy"], "unknown")
        self.assertFalse(report["production_ready"])
        self.assertFalse((self.data / "knowledge.sqlite3").exists())

    def test_secure_checks_and_backup_must_be_separate(self):
        self.write_config(cookie_secure=False, allowed_hosts=["localhost", "rag.internal.example"])
        report = run_preflight(self.config, self.data / "backups")
        checks = {item["code"]: item["status"] for item in report["checks"]}
        self.assertEqual(checks["secure_cookie"], "fail")
        self.assertEqual(checks["deployment_host"], "fail")
        self.assertEqual(checks["backup_directory"], "fail")
        self.assertFalse((self.data / "backups").exists())

    def test_configured_checks_can_pass_without_claiming_production_ready(self):
        self.write_config()
        with patch("zhiwiki.service.preflight.importlib.util.find_spec", return_value=object()):
            report = run_preflight(self.config, self.backup)
        self.assertTrue(report["blocking_checks_passed"])
        self.assertFalse(report["production_ready"])
        self.assertTrue(any(item["status"] == "unknown" for item in report["checks"]))

    def test_environment_path_is_rejected_before_open(self):
        # No file is created or read; the path guard must reject this name.
        with self.assertRaises(ValueError):
            run_preflight(self.root / ".env")

    def test_missing_worker_and_data_directory_do_not_get_created(self):
        missing_data = self.root / "not-created"
        self.write_config(data_dir=str(missing_data), worker_python=str(self.root / "missing-python"))
        report = run_preflight(self.config, self.backup)
        checks = {item["code"]: item["status"] for item in report["checks"]}
        self.assertEqual(checks["data_directory"], "fail")
        self.assertEqual(checks["worker_interpreter"], "fail")
        self.assertFalse(missing_data.exists())

    def test_bad_configuration_does_not_emit_its_content(self):
        self.config.write_text('{"unexpected_secret":"do-not-log"}', encoding="utf-8")
        with patch("builtins.print") as output:
            status = main(["--config", str(self.config), "--backup-dir", str(self.backup)])
        self.assertEqual(status, 1)
        self.assertNotIn("do-not-log", str(output.call_args))


if __name__ == "__main__":
    unittest.main()
