"""JSON 接入和质检应遵循一致的严格解析规则。"""

import tempfile

import pytest
from fastapi.testclient import TestClient

from zhiwiki.api import create_app
from zhiwiki.config import Settings
from zhiwiki.data_quality import inspect_document
from zhiwiki.ingest import parse_upload


def quality_issues(text):
    """以直接录入的 JSON 文档检查质量规则。"""
    return inspect_document({
        "id": "doc_json", "title": "sample", "source_key": "sample.json", "text": text,
    })["issues"]


@pytest.mark.parametrize("constant", ["NaN", "Infinity", "-Infinity"])
def test_nonstandard_constants_rejected_by_import_and_flagged_by_quality(constant):
    text = '{"private_field":"private_value","reading":' + constant + '}'

    with pytest.raises(ValueError, match="JSON 格式无效") as error:
        parse_upload("sample.json", text.encode("utf-8"))
    issues = quality_issues(text)

    assert "invalid_json" in {issue["code"] for issue in issues}
    assert "private_value" not in str(error.value)
    assert "private_value" not in str(issues)
    assert "private_field" not in str(issues)


def test_standard_values_are_accepted_by_import_and_quality():
    text = '{"amount":1e3,"valid":true,"nothing":null,"notes":"NaN and Infinity"}'

    assert parse_upload("sample.json", text.encode("utf-8"))["text"] == text
    assert "invalid_json" not in {issue["code"] for issue in quality_issues(text)}


def test_duplicate_keys_still_flagged_for_valid_json():
    text = '{"sensitive":"old","sensitive":"new","nested":{"x":1,"x":2}}'

    assert parse_upload("sample.json", text.encode("utf-8"))["text"] == text
    issues = quality_issues(text)
    duplicate = [issue for issue in issues if issue["code"] == "duplicate_key"]
    assert len(duplicate) == 1
    assert "2 次" in duplicate[0]["message"]
    assert "sensitive" not in str(duplicate)
    assert "old" not in str(duplicate)
    assert "new" not in str(duplicate)


def test_nonstandard_constant_takes_precedence_over_duplicate_warning():
    text = '{"sensitive":"old","sensitive":"new","reading":NaN}'

    with pytest.raises(ValueError, match="JSON 格式无效"):
        parse_upload("sample.json", text.encode("utf-8"))
    codes = {issue["code"] for issue in quality_issues(text)}
    assert "invalid_json" in codes
    assert "duplicate_key" not in codes


def test_direct_document_quality_api_flags_nonstandard_json():
    """直接录入资料后，公开质检接口也应识别非法常量。"""
    text = '{"private_field":"private_value","reading":NaN}'
    with tempfile.TemporaryDirectory() as directory:
        with TestClient(create_app(Settings(data_dir=directory))) as client:
            created = client.post("/api/documents", json={
                "title": "JSON quality", "source_key": "direct.json", "text": text,
            })
            assert created.status_code == 201
            inspected = client.post("/api/data-quality/inspect", json={
                "document_ids": [created.json()["id"]],
            })
            assert inspected.status_code == 200
            issues = inspected.json()["documents"][0]["issues"]
            assert "invalid_json" in {issue["code"] for issue in issues}
            assert "private_value" not in str(issues)
