"""Run an actual worker subprocess through upload and reviewable job state."""

from test_team_service import team
from test_team_structured_upload import upload
from zhiwiki.service.worker import supervise


def test_supervisor_runs_real_parser_process_and_reports_heartbeat(team):
    client, services, _ = team
    content = b"Worker process integration sample with enough text for the quality checks."
    response = upload(team, "worker-sample.txt", content, "worker-process")
    assert response.status_code == 202

    # Launch the configured Python interpreter as the production supervisor does.
    supervise(services.settings, once=True)

    job = client.get("/v1/workspaces/default/jobs/" + response.json()["job_id"])
    assert job.status_code == 200
    assert job.json()["status"] in ("needs_review", "awaiting_publish")
    assert job.json()["pages_done"] == 1
    assert client.get("/health/worker").status_code == 200
