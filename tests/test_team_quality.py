"""Quality hints track staged revisions and are refreshed after correction."""

import time

from test_team_service import headers, team  # noqa: F401 - pytest fixture
from zhiwiki.service.worker import process_job


def test_import_quality_correction_and_authorization(team):
    client, services, ids = team
    upload = client.post(
        "/v1/workspaces/default/uploads?knowledge_base_id=" + ids["kb"],
        headers=headers(key="quality-upload-" + str(time.time_ns())),
        data={"knowledge_base_id": ids["kb"], "mode": "new", "logical_source_key": "quality-test"},
        files={"file": ("quality.txt", "这是包含替换字符的待核对资料：�，需要人工校验并明确来源。".encode())},
    )
    assert upload.status_code == 202, upload.text
    claimed = services.jobs.claim()
    process_job(services.settings, claimed["id"], claimed["fence"])
    job = services.jobs.get(services.auth.principal(client.cookies["zw_session"]), claimed["id"])
    assert job["status"] == "needs_review"
    assert job["quality_summary"]["flagged_pages"] == 1
    path = "/v1/workspaces/default/documents/{}/revisions/{}".format(job["document_id"], job["revision_id"])
    page = client.get(path + "/pages/1").json()
    assert any(item["code"] == "replacement_character" for item in page["quality"]["rule_issues"])
    assert client.get(path + "/pages/1", headers=headers(ids["token"])).status_code == 403
    corrected = "这是已经人工校核并确认来源的资料正文，保留原始记录供审计人员核查。"
    response = client.put(path + "/pages/1", json={"text": corrected, "expected_text_sha256": page["text_sha256"], "note": "人工确认内容并修正字符"})
    assert response.status_code == 200, response.text
    updated = client.get(path + "/pages/1").json()
    assert updated["raw_text"] == page["raw_text"]
    assert updated["text"] == corrected
    assert updated["quality"]["manually_corrected"] is True
    assert "rule_issues" not in updated["quality"]
    revision = client.get(path).json()
    assert revision["quality"]["flagged_pages"] == 0
    assert revision["reviewed"] is False
    assert revision["status"] == "needs_review"
    stale = client.put(path + "/pages/1", json={"text": corrected, "expected_text_sha256": page["text_sha256"], "note": "重复提交校验冲突"})
    assert stale.status_code == 412
