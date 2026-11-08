"""Worker heartbeat monitoring is separate from API readiness."""

import time

import pytest

from test_team_service import team


@pytest.mark.parametrize("heartbeat,expected", [
    (None, 503),
    ("current", 200),
    ("stale", 503),
    ("future", 503),
    ("not-a-number", 503),
    ("nan", 503),
])
def test_worker_health_reflects_heartbeat_without_requiring_login(team, heartbeat, expected):
    client, services, _ = team
    if heartbeat is not None:
        values = {"current": str(time.time()), "stale": str(time.time() - 31),
                  "future": str(time.time() + 60)}
        with services.db.tx(write=True) as connection:
            connection.execute("INSERT OR REPLACE INTO team_runtime VALUES('worker_heartbeat',?)",
                               (values.get(heartbeat, heartbeat),))
    client.cookies.clear()

    response = client.get("/health/worker")

    assert response.status_code == expected
    assert response.json() == {"status": "alive" if expected == 200 else "unavailable"}
