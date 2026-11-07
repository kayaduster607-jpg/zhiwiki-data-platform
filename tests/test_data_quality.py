"""文档质检接口测试：验证规则、边界和只读行为。"""

import tempfile
import unittest

from fastapi.testclient import TestClient

from zhiwiki.api import create_app
from zhiwiki.config import Settings


class DataQualityTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.client = TestClient(create_app(Settings(data_dir=self.temp.name)))

    def tearDown(self):
        self.client.close()
        self.temp.cleanup()

    def test_issue_detection_and_no_document_changes(self):
        # 重复内容可能是正常排版，质检只能提示，不能静默修改。
        text = "这是重复内容用于测试质检规则\n" * 3 + "编码异常：\ufffd"
        document = self.client.post("/api/documents", json={
            "title": "质检资料", "source_key": "quality-case", "text": text,
        }).json()
        before = self.client.get("/api/documents/" + document["id"]).json()
        response = self.client.post("/api/data-quality/inspect", json={"document_ids": [document["id"]]})
        self.assertEqual(response.status_code, 200)
        report = response.json()
        self.assertEqual(report["summary"], {"total": 1, "issue_count": 2})
        item = report["documents"][0]
        self.assertEqual({issue["code"] for issue in item["issues"]}, {"replacement_character", "repeated_lines"})
        self.assertEqual(item["stats"], {"characters": len(text), "lines": len(text.splitlines())})
        self.assertEqual(before, self.client.get("/api/documents/" + document["id"]).json())

    def test_invalid_and_unknown_ids(self):
        url = "/api/data-quality/inspect"
        for ids in ([], ["a", "b"], [" "]):
            self.assertEqual(self.client.post(url, json={"document_ids": ids}).status_code, 422)
        self.assertEqual(self.client.post(url, json={"document_ids": ["missing"]}).status_code, 404)
        self.assertEqual(self.client.post(url, json={"document_ids": ["a"], "extra": True}).status_code, 422)

    def test_short_and_clean_documents(self):
        url = "/api/data-quality/inspect"
        short = self.client.post("/api/documents", json={
            "title": "短文", "source_key": "short", "text": "简短资料",
        }).json()
        result = self.client.post(url, json={"document_ids": [short["id"]]}).json()
        self.assertEqual(result["documents"][0]["issues"][0]["code"], "short_text")
        clean = self.client.post("/api/documents", json={
            "title": "正常资料", "source_key": "clean", "text": "这是包含完整段落的普通资料。" * 4,
        }).json()
        result = self.client.post(url, json={"document_ids": [clean["id"]]}).json()
        self.assertEqual(result["summary"]["issue_count"], 0)


if __name__ == "__main__":
    unittest.main()
