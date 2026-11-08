"""New data formats preserve source text and reject malformed inputs."""

import unittest

from zhiwiki.data_quality import inspect_document
from zhiwiki.ingest import parse_upload


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

    def test_json_quality_reports_nested_duplicate_count_without_field_data(self):
        text = ('{"outer":"顶层敏感值","outer":"覆盖后的顶层敏感值",'
                '"nested":{"token":"嵌套敏感值","token":"第二个嵌套敏感值","token":"最终嵌套敏感值"},'
                '"items":[{"name":"甲"},{"name":"乙"}]}')
        document = {"id": "doc_json", "title": "JSON", "source_key": "file.json", "text": text}

        report = inspect_document(document)

        self.assertEqual(report["issues"], [{
            "code": "duplicate_key",
            "severity": "warning",
            "message": "JSON 存在 3 次重复键，请人工核对。",
        }])
        issue_output = str(report["issues"])
        for field_data in ("outer", "nested", "token", "顶层敏感值", "覆盖后的顶层敏感值",
                           "嵌套敏感值", "第二个嵌套敏感值", "最终嵌套敏感值"):
            with self.subTest(field_data=field_data):
                self.assertNotIn(field_data, issue_output)
        self.assertEqual(document["text"], text)
        self.assertEqual(report["stats"], {"characters": len(text), "lines": 1})

    def test_json_quality_does_not_merge_same_named_keys_across_objects(self):
        text = '[{"name":"甲"},{"name":"乙"},{"child":{"name":"丙"}},{"child":{"name":"丁"}}]'
        document = {"id": "doc_json", "title": "JSON", "source_key": "file.json", "text": text}

        report = inspect_document(document)

        self.assertEqual(report["issues"], [])
        self.assertEqual(document["text"], text)


if __name__ == "__main__":
    unittest.main()
