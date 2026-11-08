"""Backup recovery must fail closed when referenced artifacts are incomplete."""

import json

import pytest
from fastapi.testclient import TestClient

from test_team_service import headers, publish_text, team
from zhiwiki.service.api import create_service_app
from zhiwiki.service.common import ServiceSettings
from zhiwiki.service.operations import backup_workspace, restore_workspace


@pytest.fixture
def backup_root(tmp_path_factory):
    """Keep backup destinations outside the live team's data directory."""
    return tmp_path_factory.mktemp("backup-case")


@pytest.mark.parametrize("prefix", ["uploads/", "indexes/"])
def test_restore_rejects_manifest_missing_referenced_artifacts(team, backup_root, prefix):
    publish_text(team)
    snapshot = backup_root / "snapshot"
    target = backup_root / "restored"
    backup_workspace(team[1].settings, snapshot)

    manifest_path = snapshot / "manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    missing = next(name for name in manifest["files"] if name.startswith(prefix))
    del manifest["files"][missing]
    manifest_path.write_text(json.dumps(manifest), encoding="utf-8")

    with pytest.raises(ValueError, match="database references"):
        restore_workspace(snapshot, target)
    assert not target.exists()


def test_backup_rejects_corrupted_content_addressed_upload(team, backup_root):
    result = publish_text(team)
    services = team[1]
    with services.db.tx() as connection:
        checksum = connection.execute(
            "SELECT file_hash FROM team_revisions WHERE id=?", (result["revision_id"],)
        ).fetchone()[0]
    (services.db.root / "uploads" / checksum).write_bytes(b"corrupted upload")
    snapshot = backup_root / "snapshot"

    with pytest.raises(ValueError, match="content address mismatch"):
        backup_workspace(services.settings, snapshot)
    assert not (snapshot / "manifest.json").exists()


def test_restore_rejects_member_with_hash_changed_to_match_corrupt_content(team, backup_root):
    publish_text(team)
    snapshot = backup_root / "snapshot"
    target = backup_root / "restored"
    backup_workspace(team[1].settings, snapshot)
    manifest_path = snapshot / "manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    upload = next(name for name in manifest["files"] if name.startswith("uploads/"))
    (snapshot / upload).write_bytes(b"corrupted upload")

    # A matching manifest checksum alone must not override the filename address.
    import hashlib
    manifest["files"][upload] = hashlib.sha256(b"corrupted upload").hexdigest()
    manifest_path.write_text(json.dumps(manifest), encoding="utf-8")
    with pytest.raises(ValueError, match="content address mismatch"):
        restore_workspace(snapshot, target)
    assert not target.exists()


def test_restored_workspace_supports_authorized_search(team, backup_root):
    """Exercise the restored database, index, credentials, and API together."""
    publish_text(team)
    snapshot = backup_root / "snapshot"
    target = backup_root / "restored"
    backup_workspace(team[1].settings, snapshot)
    restore_workspace(snapshot, target)
    app = create_service_app(ServiceSettings(data_dir=str(target), cookie_secure=False))

    with TestClient(app) as client:
        response = client.post(
            "/v1/workspaces/default/retrievals",
            headers=headers(team[2]["token"], key="restored-search-01"),
            json={"query": "Return policy", "knowledge_base_ids": [team[2]["kb"]]},
        )

    assert response.status_code == 200
    assert "Return policy" in response.json()["evidence"][0]["text"]
