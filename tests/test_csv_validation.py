"""CSV import and quality checks classify field limits consistently."""

import csv
from concurrent.futures import ThreadPoolExecutor

import pytest

from zhiwiki.data_quality import inspect_document
from zhiwiki.ingest import MAX_TEXT_CHARS, parse_upload


def issues(text):
    """Run the same quality rule used by local and team imports."""
    return inspect_document({"id": "sample", "title": "sample", "source_key": "sample.csv", "text": text})["issues"]


def test_csv_field_limit_is_reported_without_field_content():
    limit = csv.field_size_limit()
    if limit + 10 > MAX_TEXT_CHARS:
        pytest.skip("Runtime CSV field limit exceeds the document text limit")
    content = "name\n" + ("secret" * (limit // 6 + 1))[:limit + 1] + "\n"

    with pytest.raises(ValueError, match="CSV 单字段超过") as error:
        parse_upload("sample.csv", content.encode("utf-8"))
    flagged = issues(content)

    assert str(limit) in str(error.value)
    assert "secret" not in str(error.value)
    assert "csv_field_too_large" in {item["code"] for item in flagged}
    assert "secret" not in str(flagged)
    assert csv.field_size_limit() == limit


def test_csv_at_current_field_limit_remains_accepted():
    limit = csv.field_size_limit()
    if limit + 10 > MAX_TEXT_CHARS:
        pytest.skip("Runtime CSV field limit exceeds the document text limit")
    content = "name\n" + "a" * limit + "\n"
    assert parse_upload("sample.csv", content.encode("utf-8"))["text"] == content
    assert not {"invalid_csv", "csv_field_too_large"} & {issue["code"] for issue in issues(content)}


def test_malformed_csv_is_distinct_from_field_limit_error():
    content = 'name\n"unterminated'
    with pytest.raises(ValueError, match="CSV 解析失败"):
        parse_upload("sample.csv", content.encode("utf-8"))
    assert "invalid_csv" in {item["code"] for item in issues(content)}


def test_concurrent_csv_checks_do_not_change_the_process_limit():
    limit = csv.field_size_limit()
    if limit + 10 > MAX_TEXT_CHARS:
        pytest.skip("Runtime CSV field limit exceeds the document text limit")
    contents = ["name\n" + "x" * size + "\n" for size in (limit, limit + 1)] * 3
    with ThreadPoolExecutor(max_workers=4) as pool:
        results = list(pool.map(issues, contents))
    assert all(("csv_field_too_large" in {item["code"] for item in result}) == (index % 2 == 1)
               for index, result in enumerate(results))
    assert csv.field_size_limit() == limit
