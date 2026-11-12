"""Exercise the real service/worker/browser with generated, isolated credentials.

No project settings or environment files are loaded. Browser dependencies are
explicit CLI arguments, so production installs do not require a frontend toolchain.
"""

import argparse
import json
from pathlib import Path
import secrets
import socket
import subprocess
import sys
import tempfile
import threading
import time

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import uvicorn
from fastapi.testclient import TestClient

from zhiwiki.service.api import create_service_app
from zhiwiki.service.common import ServiceSettings, safe_path
from zhiwiki.service.operations import backup_workspace, restore_workspace


def available_port():
    with socket.socket() as listener:
        listener.bind(("127.0.0.1", 0))
        return listener.getsockname()[1]


def start_service(settings):
    app = create_service_app(settings)
    password = secrets.token_urlsafe(24)
    app.state.services.auth.create_user("workbench_admin", password, True)
    port = available_port()
    server = uvicorn.Server(uvicorn.Config(app, host="127.0.0.1", port=port, log_level="error", access_log=False))
    thread = threading.Thread(target=server.run, daemon=True)
    thread.start()
    stop = time.monotonic() + 20
    while not server.started and thread.is_alive() and time.monotonic() < stop:
        time.sleep(0.05)
    if not server.started:
        raise RuntimeError("Isolated API did not start")
    return server, thread, port, password


def stop_process(process):
    """Terminate only the worker created by this verification process."""
    if process.poll() is None:
        process.terminate()
        try:
            process.wait(timeout=10)
        except subprocess.TimeoutExpired:
            process.kill()
            process.wait(timeout=5)


def verify_restore(settings, run_root, password):
    snapshot = run_root / "snapshot"
    restored = run_root / "restored"
    backup_workspace(settings, snapshot)
    restore_workspace(snapshot, restored)
    app = create_service_app(ServiceSettings(data_dir=str(restored), cookie_secure=False))
    with TestClient(app) as client:
        login = client.post("/v1/sessions", json={"username": "workbench_admin", "password": password})
        assert login.status_code == 200
        directory = client.get("/v1/workspaces/default/documents", params={"knowledge_base_id": "browser_kb"})
        assert directory.status_code == 200
        assert any(row["current_number"] == 2 for row in directory.json()["documents"])
        members = client.get("/v1/workspaces/default/knowledge-bases/browser_kb/members")
        assert any(row["username"] == "workbench_reader" for row in members.json()["members"])
    return {"database_original_files_and_grants_restored": True, "published_revision": 2}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", required=True)
    parser.add_argument("--node", default="node")
    parser.add_argument("--playwright-module", default="playwright")
    parser.add_argument("--browser")
    parser.add_argument("--record-video", action="store_true", help="Record an annotated walkthrough with synthetic data")
    args = parser.parse_args()
    output = safe_path(args.output)
    output.mkdir(parents=True, exist_ok=True)
    run_root = Path(tempfile.mkdtemp(prefix="workbench-run-", dir=output)).resolve()
    assert run_root.parent == output
    settings = ServiceSettings(data_dir=str(run_root / "data"), cookie_secure=False,
        user_rpm=6000, global_rpm=60000, user_burst=600, global_burst=6000)
    config = run_root / "worker.json"
    config.write_text(json.dumps({"data_dir": settings.data_dir}), encoding="utf-8")
    server, thread, port, password = start_service(settings)
    command = [sys.executable, "-B", "-m", "zhiwiki.service", "--config", str(config), "worker"]
    with (run_root / "worker.log").open("w", encoding="utf-8") as log:
        worker = subprocess.Popen(command, cwd=Path(__file__).resolve().parents[1], stdout=log, stderr=log)
        try:
            payload = {"base_url": "http://127.0.0.1:" + str(port), "admin_password": password,
                       "reader_password": secrets.token_urlsafe(24), "output": str(run_root), "browser": args.browser,
                       "record_video": args.record_video}
            result = subprocess.run([args.node, str(Path(__file__).with_suffix(".cjs")), args.playwright_module],
                input=json.dumps(payload), text=True, encoding="utf-8", capture_output=True, timeout=300)
            if result.returncode:
                raise RuntimeError("Browser verification failed:\n" + result.stderr[-10000:])
            browser_report = json.loads(result.stdout)
        finally:
            stop_process(worker)
            server.should_exit = True
            thread.join(timeout=10)
    report = {"browser": browser_report, "restore": verify_restore(settings, run_root, password),
              "scope": "isolated local API, real worker process and browser; no production SLA claim"}
    (output / "browser-verification.json").write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({"result": "passed", "report": str(output / "browser-verification.json"),
                      "screenshots": str(run_root), "checks": browser_report["checks"], "video": browser_report.get("video")}, ensure_ascii=False))


if __name__ == "__main__":
    main()
