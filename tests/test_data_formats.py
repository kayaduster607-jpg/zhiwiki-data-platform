"""New data formats preserve source text and reject malformed inputs."""

import unittest

from zhiwiki.ingest import parse_upload
from zhiwiki.data_quality import inspect_document


class StructuredInputTests(unittest.TestCase):
    def test_json_and_csv_preserve_original_text(self):
        for filename, text in [("a.json", '{"项目": "心桥"}'), ("a.csv", '名称,状态\n"规则,一",有效')]:
            with self.subTest(filename=filename):
                self.assertEqual(parse_upload(filename, text.encode("utf-8"))["text"], text)

    def test_malformed_formats_are_rejected(self):
        for filename, raw in [("a.json", b'{"broken":'), ("a.csv", b'"unfinished')]:
            with self.subTest(filename=filename):
                with self.assertRaises(ValueError):
                    parse_upload(filename, raw)

    def test_csv_quality_reports_duplicate_and_inconsistent_columns(self):
        report = inspect_document({"id": "doc_test", "title": "表格", "source_key": "file.csv",
                                   "text": "姓名,姓名,\n甲,乙\n丙,丁,戊,额外"})
        codes = {issue["code"] for issue in report["issues"]}
        self.assertTrue({"empty_header", "duplicate_header", "inconsistent_columns"}.issubset(codes))


if __name__ == "__main__":
    unittest.main()
