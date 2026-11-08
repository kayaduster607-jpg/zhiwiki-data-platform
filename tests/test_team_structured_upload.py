"""Team imports keep source bytes, require review and enforce access limits."""

import csv
import hashlib
import time

import pytest

from test_team_service import headers, retrieve, team
from zhiwiki.service.worker import process_job


def upload(team, filename, content, key, mode="new", document=None, revision=None):
    """Submit through the same authenticated HTTP boundary as enterprise clients."""
    client, _, identities = team
    fields = {"knowledge_base_id": identities["kb"], "mode": mode, "logical_source_key": key}
    if document:
        fields.update(document_id=document, expected_revision_id=revision)
    return client.post(
        "/v1/workspaces/default/uploads?knowledge_base_id=" + identities["kb"],
        headers=headers(key="upload-" + str(time.time_ns())), data=fields,
        files={"file": (filename, content, "application/octet-stream")},
    )


def process(team, job_id):
    """Run the actual worker and read the resulting authenticated job state."""
    client, services, _ = team
    claimed = services.jobs.claim()
    assert claimed and claimed["id"] == job_id
    process_job(services.settings, claimed["id"], claimed["fence"])
    return services.jobs.get(services.auth.principal(client.cookies["zw_session"]), job_id)


def review_and_publish(team, result, previous=None):
    client, _, _ = team
    path = "/v1/workspaces/default/documents/{}/revisions/{}".format(result["document_id"], result["revision_id"])
    response = client.post(path + ":review", json={"note": "Reviewed imported source data"})
    assert response.status_code == 200, response.text
    condition = {"If-Match": '"' + previous + '"'} if previous else {"If-None-Match": "*"}
    response = client.post(path + ":publish", headers=headers(key="pub-" + str(time.time_ns()), **condition))
    assert response.status_code == 200, response.text
    return path


@pytest.mark.parametrize("filename,content", [
    ("records.csv", '名称,说明\r\n甲,"首行\r\n次行"\r\n'.encode("utf-8")),
    ("records.json", '{\r\n  "名称": "星舟", "数量": 3\r\n}'.encode("utf-8")),
])
def test_structured_sources_follow_review_and_preserve_bytes(team, filename, content):
    client, _, _ = team
    response = upload(team, filename, content, filename)
    assert response.status_code == 202, response.text
    result = process(team, response.json()["job_id"])
    # Both intentionally short samples are now flagged for human review.
    assert result["status"] == "needs_review"
    assert result["quality_summary"]["flagged_pages"] == 1
    path = "/v1/workspaces/default/documents/{}/revisions/{}".format(result["document_id"], result["revision_id"])
    page = client.get(path + "/pages/1")
    assert page.status_code == 200, page.text
    assert page.json()["raw_text"] == content.decode("utf-8")
    assert "short_text" in {issue["code"] for issue in page.json()["quality"]["rule_issues"]}
    # Raw file download comes from the immutable, content-addressed original.
    assert client.get(path + "/file").content == content
    review_and_publish(team, result)
    term = "首行" if filename.endswith(".csv") else "星舟"
    answer = retrieve(team, key="search-" + str(time.time_ns()), query=term)
    assert answer.status_code == 200, answer.text
    assert any(term in item["text"] for item in answer.json()["evidence"])


def test_new_version_keeps_old_structured_source(team):
    client, _, _ = team
    first = upload(team, "data.json", b'{"value":1}', "data")
    old = process(team, first.json()["job_id"])
    old_path = review_and_publish(team, old)
    second = upload(team, "data.json", b'{"value":2}', "data", "update", old["document_id"], old["revision_id"])
    assert second.status_code == 202, second.text
    new = process(team, second.json()["job_id"])
    review_and_publish(team, new, old["revision_id"])
    assert client.get(old_path + "/file").content == b'{"value":1}'


def test_invalid_json_correction_never_replaces_valid_staged_page(team):
    client, _, _ = team
    response = upload(team, "source.json", b'{"value":1}', "correction-test")
    result = process(team, response.json()["job_id"])
    path = "/v1/workspaces/default/documents/{}/revisions/{}/pages/1".format(result["document_id"], result["revision_id"])
    original = client.get(path).json()
    rejected = client.put(path, json={"text": '{"value":NaN}',
                                     "expected_text_sha256": original["text_sha256"],
                                     "note": "检查无效内容是否被拒绝"})
    assert rejected.status_code == 422
    assert client.get(path).json()["text"] == original["text"]


def test_same_bytes_with_new_format_get_new_processing_job(team):
    content = b"column,column\nfirst,second\n"
    first = upload(team, "source.txt", content, "same-source")
    old = process(team, first.json()["job_id"])
    review_and_publish(team, old)
    updated = upload(team, "source.csv", content, "same-source", "update", old["document_id"], old["revision_id"])
    assert updated.status_code == 202, updated.text
    assert updated.json()["unchanged"] is False
    result = process(team, updated.json()["job_id"])
    path = "/v1/workspaces/default/documents/{}/revisions/{}/pages/1".format(result["document_id"], result["revision_id"])
    quality = team[0].get(path).json()["quality"]
    assert "duplicate_header" in {item["code"] for item in quality["rule_issues"]}


def test_long_csv_field_returns_actionable_worker_error(team):
    limit = csv.field_size_limit()
    if limit + 10 > 500_000:
        pytest.skip("Runtime CSV field limit exceeds the document text limit")
    content = ("name\n" + "x" * (limit + 1) + "\n").encode("utf-8")
    response = upload(team, "large-field.csv", content, "large-field")
    assert response.status_code == 202, response.text
    job = process(team, response.json()["job_id"])
    assert job["status"] == "failed"
    assert job["error"] == "CSV_FIELD_TOO_LARGE"


def test_upload_rejects_corrupt_existing_content_addressed_blob(team):
    content = b"valid original content that should be stored safely"
    checksum = hashlib.sha256(content).hexdigest()
    target = team[1].db.root / "uploads" / checksum
    corrupt = b"x" * len(content)
    target.write_bytes(corrupt)

    response = upload(team, "sample.txt", content, "corrupt-existing")

    assert response.status_code == 503
    assert response.json()["error"]["code"] == "UPLOAD_STORE_CORRUPTED"
    assert target.read_bytes() == corrupt
    assert not list(target.parent.glob("*.pending"))


def test_old_pipeline_result_does_not_skip_new_quality_rules(team):
    client, services, _ = team
    first = upload(team, "source.txt", b"Some text with enough length for this test.", "pipeline-source")
    old = process(team, first.json()["job_id"])
    review_and_publish(team, old)
    # Simulate a revision created by the previous deployed processing version.
    with services.db.tx(write=True) as connection:
        connection.execute("UPDATE team_revisions SET pipeline=? WHERE id=?", ("old-pipeline", old["revision_id"]))
    updated = upload(team, "source.txt", b"Some text with enough length for this test.",
                     "pipeline-source", "update", old["document_id"], old["revision_id"])
    assert updated.status_code == 202, updated.text
    assert updated.json()["unchanged"] is False
    assert process(team, updated.json()["job_id"])["revision_id"] != old["revision_id"]


def test_legacy_json_is_rechecked_after_quality_rule_upgrade(team, monkeypatch):
    """A matching legacy file must not reuse a result from before the new rule."""
    import zhiwiki.service.jobs as jobs_module
    import zhiwiki.service.worker as worker_module

    client, _, _ = team
    content = b'{"code":"legacy","code":"new","description":"A long example for the quality rules"}'
    original_assess = worker_module.assess_page

    def legacy_assess(filename, text, **kwargs):
        # Model the previously deployed rule set while retaining other warnings.
        result = original_assess(filename, text, **kwargs)
        remaining = [issue for issue in result.get("rule_issues", []) if issue["code"] != "duplicate_key"]
        if remaining:
            result["rule_issues"] = remaining
        else:
            result.pop("rule_issues", None)
        return result

    with monkeypatch.context() as legacy:
        legacy.setattr(jobs_module, "PIPELINE", "pdf-text-nfkc-visible-glyphs-fixed900-120-quality-v2")
        legacy.setattr(worker_module, "assess_page", legacy_assess)
        first = upload(team, "legacy.json", content, "legacy-quality")
        assert first.status_code == 202, first.text
        old = process(team, first.json()["job_id"])
        old_path = review_and_publish(team, old)

    old_page = client.get(old_path + "/pages/1").json()
    assert "duplicate_key" not in {issue["code"] for issue in old_page["quality"].get("rule_issues", [])}

    updated = upload(team, "legacy.json", content, "legacy-quality", "update", old["document_id"], old["revision_id"])
    assert updated.status_code == 202, updated.text
    assert updated.json()["unchanged"] is False
    current = process(team, updated.json()["job_id"])
    assert current["revision_id"] != old["revision_id"]
    current_path = "/v1/workspaces/default/documents/{}/revisions/{}".format(current["document_id"], current["revision_id"])
    page = client.get(current_path + "/pages/1").json()
    assert page["raw_text"].encode("utf-8") == content
    assert "duplicate_key" in {issue["code"] for issue in page["quality"]["rule_issues"]}
    assert client.get(old_path + "/pages/1").json()["quality"] == old_page["quality"]

    # Once published under the new pipeline, identical uploads remain deduplicated.
    review_and_publish(team, current, old["revision_id"])
    repeated = upload(team, "legacy.json", content, "legacy-quality", "update", current["document_id"], current["revision_id"])
    assert repeated.status_code == 202, repeated.text
    assert repeated.json()["unchanged"] is True
    assert repeated.json()["job_id"] == current["job_id"]


@pytest.mark.parametrize("filename,content", [
    ("bad.json", b'{"bad":'), ("bad.csv", b'"unterminated'),
    ("bad-constant.json", b'{"value":NaN}'),
])
def test_malformed_structured_source_fails_before_review(team, filename, content):
    client, services, _ = team
    response = upload(team, filename, content, filename)
    assert response.status_code == 202, response.text
    claimed = services.jobs.claim()
    with pytest.raises(ValueError):
        process_job(services.settings, claimed["id"], claimed["fence"])
    result = services.jobs.get(services.auth.principal(client.cookies["zw_session"]), claimed["id"])
    assert result["status"] == "failed"
    path = "/v1/workspaces/default/documents/{}/revisions/{}".format(result["document_id"], result["revision_id"])
    assert client.post(path + ":review", json={"note": "Reviewed invalid source"}).status_code == 409


def test_reader_cannot_import_and_size_limit_is_enforced(team):
    client, _, identities = team
    fields = {"knowledge_base_id": identities["kb"], "mode": "new", "logical_source_key": "not-allowed"}
    denied = client.post("/v1/workspaces/default/uploads?knowledge_base_id=" + identities["kb"],
                         headers=headers(identities["token"]), data=fields,
                         files={"file": ("data.csv", b"a,b\n1,2", "text/csv")})
    assert denied.status_code == 403
    response = upload(team, "large.csv", b"a" * (2 * 1024 * 1024 + 1), "large")
    assert response.status_code == 413
