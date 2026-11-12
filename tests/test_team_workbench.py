"""Workbench lists obey current access, stable pagination and publication state."""

import time

import pytest

from test_team_service import headers, publish_text, team  # noqa: F401
from zhiwiki.service.worker import process_job


BASE = "/v1/workspaces/default"


def upload(team, key="source-one"):
    client, _, ids = team
    response = client.post(BASE + "/uploads?knowledge_base_id=" + ids["kb"],
        headers=headers(key="workbench-" + key),
        data={"knowledge_base_id": ids["kb"], "mode": "new", "logical_source_key": key},
        files={"file": (key + ".txt", b"A documented return policy with an explicit source and review.")})
    assert response.status_code == 202, response.text
    return response.json()


def session(services, username, kb, role):
    user = services.auth.create_user(username, username + "-test-password")
    services.auth.grant(user, kb, role)
    issued = services.auth.issue(user, kind="session", scopes=["*"])
    return user, {"Cookie": "zw_session=" + issued["token"], "X-CSRF-Token": issued["csrf"]}


def test_job_pages_are_bounded_and_bound_to_list_filters_and_owner(team):
    client, services, ids = team
    expected = {upload(team, "source-" + str(index))["job_id"] for index in range(3)}
    params = {"knowledge_base_id": ids["kb"], "limit": 1}
    first = client.get(BASE + "/jobs", params=params).json()
    cursor = first["next_cursor"]
    assert cursor and len(first["jobs"]) == 1
    seen = [first["jobs"][0]["job_id"]]
    while cursor:
        page = client.get(BASE + "/jobs", params={**params, "cursor": cursor})
        assert page.status_code == 200
        seen.extend(item["job_id"] for item in page.json()["jobs"])
        cursor = page.json()["next_cursor"]
    assert len(seen) == len(set(seen)) == 3 and set(seen) == expected
    cursor = first["next_cursor"]
    for path, changes in [("/jobs", {"status": "failed"}), ("/jobs", {"limit": 2}), ("/review-queue", {})]:
        response = client.get(BASE + path, params={**params, **changes, "cursor": cursor})
        assert response.status_code == 400 and response.json()["error"]["code"] == "INVALID_CURSOR"
    _, another = session(services, "other_editor", ids["kb"], "editor")
    assert client.get(BASE + "/jobs", params={**params, "cursor": cursor}, headers=another).status_code == 400


def test_cursor_expiry_acl_change_and_tampering_are_rejected(team, monkeypatch):
    client, services, ids = team
    upload(team, "alpha"); upload(team, "beta")
    params = {"knowledge_base_id": ids["kb"], "limit": 1}
    cursor = client.get(BASE + "/jobs", params=params).json()["next_cursor"]
    for bad in ["%%%", cursor[:-4] + "AAAA", "a" * 2049]:
        assert client.get(BASE + "/jobs", params={**params, "cursor": bad}).status_code == 400
    services.auth.grant(ids["reader"], ids["kb"], "reader")
    assert client.get(BASE + "/jobs", params={**params, "cursor": cursor}).status_code == 400
    current = client.get(BASE + "/jobs", params=params).json()["next_cursor"]
    now = time.time()
    monkeypatch.setattr("zhiwiki.service.cursors.time.time", lambda: now + 601)
    assert client.get(BASE + "/jobs", params={**params, "cursor": current}).status_code == 400


def test_library_role_is_real_and_unpublished_directory_is_not_public(team):
    client, services, ids = team
    item = upload(team)
    assert client.get(BASE + "/jobs/" + item["job_id"]).json()["knowledge_base_id"] == ids["kb"]
    assert client.get(BASE + "/knowledge-bases").json()["knowledge_bases"][0]["role"] == "admin"
    reader_headers = headers(ids["token"])
    assert client.get(BASE + "/documents", params={"knowledge_base_id": ids["kb"]}, headers=reader_headers).json()["documents"] == []
    _, editor_headers = session(services, "editor", ids["kb"], "editor")
    directory = client.get(BASE + "/documents", params={"knowledge_base_id": ids["kb"]}, headers=editor_headers).json()
    assert directory["documents"][0]["source_key"] == "source-one"
    assert directory["documents"][0]["current_revision"] is None
    assert client.get(BASE + "/jobs/" + item["job_id"], headers=reader_headers).status_code == 403


def test_tokens_cannot_observe_staged_task_or_revision_even_with_editor_owner(team):
    client, services, ids = team
    item = upload(team)
    token = services.auth.issue(ids["admin"], kb_ids=[ids["kb"]])["token"]
    credential = headers(token)
    assert client.get(BASE + "/jobs/" + item["job_id"], headers=credential).status_code == 403
    path = BASE + "/documents/" + item["document_id"] + "/revisions/" + item["revision_id"]
    assert client.get(path, headers=credential).status_code == 403
    assert client.get(path + "/pages/1", headers=credential).status_code == 403
    assert client.get(BASE + "/documents", params={"knowledge_base_id": ids["kb"]}, headers=credential).json()["documents"] == []


@pytest.mark.parametrize("path", ["/jobs", "/review-queue"])
def test_lists_recheck_current_roles_workspace_and_knowledge_base(team, path):
    client, services, ids = team
    params = {"knowledge_base_id": ids["kb"]}
    user, auth = session(services, "limited_editor", ids["kb"], "editor")
    assert client.get(BASE + path, params=params, headers=auth).status_code == 200
    secret = services.auth.create_kb("Private source", "kb_private")
    assert client.get(BASE + path, params={"knowledge_base_id": secret}, headers=auth).status_code == 403
    services.auth.grant(user, ids["kb"], "reader")
    assert client.get(BASE + path, params=params, headers=auth).status_code == 403
    assert client.get(BASE.replace("default", "other") + path, params=params).status_code == 404
    assert client.get(BASE + path, params=params, headers=headers(ids["token"])).status_code == 403


def test_review_queue_tracks_correction_review_and_publication(team):
    client, services, ids = team
    item = upload(team)
    params = {"knowledge_base_id": ids["kb"]}
    assert client.get(BASE + "/review-queue", params=params).json()["revisions"] == []
    claimed = services.jobs.claim()
    process_job(services.settings, claimed["id"], claimed["fence"])
    queued = client.get(BASE + "/review-queue", params=params).json()["revisions"][0]
    assert queued["job_id"] == item["job_id"]
    path = BASE + "/documents/" + item["document_id"] + "/revisions/" + item["revision_id"]
    assert client.post(path + ":review", json={"note": "Reviewed source and applicable policy"}).status_code == 200
    page = client.get(path + "/pages/1").json()
    corrected = client.put(path + "/pages/1", json={"text": page["text"] + " Corrected.", "expected_text_sha256": page["text_sha256"], "note": "Corrected after review"})
    assert corrected.status_code == 200
    pending = client.get(BASE + "/review-queue", params=params).json()["revisions"][0]
    assert not pending["reviewed"] and pending["status"] == "needs_review"
    assert client.post(path + ":review", json={"note": "Reviewed the corrected policy"}).status_code == 200
    assert client.post(path + ":publish", headers=headers(key="workbench-publish", **{"If-None-Match": "*"})).status_code == 200
    assert client.get(BASE + "/review-queue", params=params).json()["revisions"] == []
    history = client.get(BASE + "/documents/" + item["document_id"] + "/revisions").json()
    assert history["current_revision"] == item["revision_id"] and history["revisions"][0]["status"] == "published"
    assert client.get(path).json()["page_count"] == 1
    assert client.get(path).json()["knowledge_base_id"] == ids["kb"]
    assert client.get(BASE + "/documents", params=params, headers=headers(ids["token"])).json()["documents"][0]["current_number"] == 1


def test_user_member_token_lists_expose_metadata_without_credentials(team):
    client, services, ids = team
    users = client.get("/v1/users").json()["users"]
    assert all(set(row) == {"id", "username", "admin", "disabled"} for row in users)
    members = client.get(BASE + "/knowledge-bases/" + ids["kb"] + "/members").json()["members"]
    assert members[0]["username"] == "reader" and members[0]["role"] == "reader"
    created = client.post("/v1/tokens", json={"knowledge_base_ids": [ids["kb"]], "scopes": ["read"]}).json()
    listing = client.get("/v1/tokens").json()
    assert created["token"] not in str(listing)
    assert listing["tokens"][0]["token_id"] == created["token_id"]
    assert not {"password", "csrf_hash", "token", "token_hash"}.intersection(listing["tokens"][0])
    assert client.delete("/v1/tokens/" + created["token_id"]).status_code == 200
    assert client.get("/v1/tokens").json()["tokens"][0]["revoked"] is True
    _, editor = session(services, "ordinary_editor", ids["kb"], "editor")
    assert client.get("/v1/users", headers=editor).status_code == 403
    assert client.get(BASE + "/knowledge-bases/" + ids["kb"] + "/members", headers=editor).status_code == 403
    assert client.get("/v1/tokens", headers=editor).json()["tokens"] == []


@pytest.mark.parametrize("path", ["/v1/users", "/v1/tokens", BASE + "/jobs", BASE + "/review-queue"])
def test_control_plane_lists_reject_agent_bearer_credentials(team, path):
    client, services, ids = team
    credential = services.auth.issue(ids["admin"], kb_ids=[ids["kb"]])["token"]
    assert client.get(path, params={"knowledge_base_id": ids["kb"]}, headers=headers(credential)).status_code == 403


def test_static_assets_csp_private_cache_and_disable_self_guard(team):
    client, services, ids = team
    page = client.get("/")
    assert "script-src 'self'" in page.headers["Content-Security-Policy"]
    assert "unsafe-inline" not in page.headers["Content-Security-Policy"]
    assert page.headers["Cache-Control"] == "no-store"
    from zhiwiki.service.web import ASSETS
    for name in ASSETS:
        result = client.get("/assets/team/" + name)
        assert result.status_code == 200 and result.headers["X-Content-Type-Options"] == "nosniff"
    assert client.get("/assets/team/schema.py").status_code == 404
    assert client.post(BASE + "/users/" + ids["admin"] + ":disable").status_code == 409
    assert client.post(BASE + "/users/not-present:disable").status_code == 404
    assert client.get("/v1/users").headers["Cache-Control"] == "no-store"
    client.cookies.clear()
    denied = client.get("/v1/users")
    assert denied.status_code == 401 and denied.headers["Cache-Control"] == "no-store"


@pytest.mark.parametrize("parameters", [{"limit": 0}, {"limit": 101}, {"status": "pretend-success"}])
def test_job_filter_limits_are_validated(team, parameters):
    client, _, ids = team
    assert client.get(BASE + "/jobs", params={"knowledge_base_id": ids["kb"], **parameters}).status_code == 422


def test_task_is_recoverable_after_service_lifecycle_restart(tmp_path):
    from fastapi.testclient import TestClient
    from zhiwiki.service.api import create_service_app
    from zhiwiki.service.common import ServiceSettings

    settings = ServiceSettings(data_dir=str(tmp_path), cookie_secure=False)
    first = create_service_app(settings)
    first.state.services.auth.create_user("restart_admin", "restart-test-password", True)
    kb = first.state.services.auth.create_kb("Restart library", "kb_restart")
    with TestClient(first) as client:
        login = client.post("/v1/sessions", json={"username": "restart_admin", "password": "restart-test-password"}).json()
        client.headers["X-CSRF-Token"] = login["csrf_token"]
        response = client.post(BASE + "/uploads?knowledge_base_id=" + kb,
            headers=headers(key="restart-upload"),
            data={"knowledge_base_id": kb, "logical_source_key": "restart-source", "mode": "new"},
            files={"file": ("restart.txt", b"Persistent import with a stable task identity.")})
        assert response.status_code == 202
        job_id = response.json()["job_id"]
        cookie = client.cookies["zw_session"]
    # A new app/database instance must recover state, not reuse an in-memory list.
    second = create_service_app(settings)
    with TestClient(second) as client:
        client.cookies.set("zw_session", cookie)
        task = client.get(BASE + "/jobs/" + job_id)
        assert task.status_code == 200 and task.json()["status"] == "queued"
        listing = client.get(BASE + "/jobs", params={"knowledge_base_id": kb}).json()
        assert listing["jobs"][0]["job_id"] == job_id


def test_editor_can_correct_but_cannot_review_or_publish(team):
    client, services, ids = team
    item = upload(team)
    claimed = services.jobs.claim()
    process_job(services.settings, claimed["id"], claimed["fence"])
    _, editor = session(services, "writing_editor", ids["kb"], "editor")
    path = BASE + "/documents/" + item["document_id"] + "/revisions/" + item["revision_id"]
    page = client.get(path + "/pages/1", headers=editor).json()
    corrected = client.put(path + "/pages/1", headers=editor,
        json={"text": page["text"] + " Verified.", "expected_text_sha256": page["text_sha256"], "note": "Checked by editor"})
    assert corrected.status_code == 200
    assert client.post(path + ":review", headers=editor, json={"note": "Cannot approve own role"}).status_code == 403
    assert client.post(path + ":publish", headers={**editor, "If-None-Match": "*", "Idempotency-Key": "editor-publish-key"}).status_code == 403
