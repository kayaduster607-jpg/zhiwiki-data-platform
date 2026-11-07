"""Exercise preview, version conflicts and dependent Wiki invalidation."""

import tempfile
import unittest

from fastapi.testclient import TestClient

from zhiwiki.api import create_app
from zhiwiki.config import Settings


class CleaningApiTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.client = TestClient(create_app(Settings(data_dir=self.temp.name)))

    def tearDown(self):
        self.client.close()
        self.temp.cleanup()

    def test_preview_is_read_only_apply_versions_and_invalidates_wiki(self):
        doc = self.client.post("/api/documents", json={"title": "规则", "source_key": "rule.md", "text": "旧规则  \n\n\n\n继续"}).json()
        draft = self.client.post("/api/wiki/draft", json={"slug": "rule", "title": "规则", "document_ids": [doc["id"]]}).json()
        self.client.post("/api/wiki/" + draft["id"] + "/publish")
        request = {"document_id": doc["id"], "expected_version": 1}
        preview = self.client.post("/api/data-quality/clean-preview", json=request)
        self.assertEqual(preview.status_code, 200, preview.text)
        self.assertTrue(preview.json()["changed"])
        self.assertEqual(self.client.get("/api/documents/" + doc["id"]).json()["text"], "旧规则  \n\n\n\n继续")
        updated = self.client.post("/api/data-quality/clean-apply", json=request)
        self.assertEqual(updated.status_code, 200, updated.text)
        self.assertEqual(updated.json()["version"], 2)
        self.assertTrue(self.client.get("/api/wiki/" + draft["id"]).json()["stale"])
        self.assertEqual(self.client.get("/api/documents/" + doc["id"]).json()["text"], "旧规则  \n\n\n\n继续")
        self.assertEqual(self.client.post("/api/data-quality/clean-apply", json=request).status_code, 409)

    def test_structured_source_is_not_cleaned(self):
        doc = self.client.post("/api/documents/upload", files={"file": ("records.csv", b'"a  \n b",c\n', "text/csv")}).json()
        response = self.client.post("/api/data-quality/clean-preview", json={"document_id": doc["id"], "expected_version": 1})
        self.assertEqual(response.status_code, 400, response.text)

    def test_structured_upload_cannot_replace_unmarked_text_source(self):
        doc = self.client.post("/api/documents", json={"title": "资料", "source_key": "notes", "text": "文本资料"}).json()
        response = self.client.post(
            "/api/documents/upload?mode=update&target_document_id=" + doc["id"] + "&expected_version=1",
            files={"file": ("data.csv", b"name,value\na,1\n", "text/csv")},
        )
        self.assertEqual(response.status_code, 400, response.text)
        self.assertEqual(self.client.get("/api/documents/" + doc["id"]).json()["text"], "文本资料")


if __name__ == "__main__":
    unittest.main()
