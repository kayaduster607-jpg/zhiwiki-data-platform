"""Credential selection cannot bypass a cookie session's CSRF requirement."""

from test_team_service import team  # Register the shared isolated service fixture.


def test_non_bearer_authorization_does_not_disable_csrf(team):
    client, _, ids = team
    payload = {"knowledge_base_ids": [ids["kb"]], "scopes": ["read"]}
    for header in ("Basic invalid", "Bearer", "bearer invalid", "Other invalid"):
        response = client.post("/v1/tokens", json=payload,
                               headers={"Authorization": header, "X-CSRF-Token": ""})
        assert response.status_code == 401
    response = client.post("/v1/tokens", json=payload, headers={"X-CSRF-Token": ""})
    assert response.status_code == 403


def test_bearer_header_is_never_replaced_by_a_valid_cookie(team):
    client, _, ids = team
    assert client.get("/v1/me", headers={"Authorization": "Bearer invalid"}).status_code == 401
    assert client.get("/v1/me", headers={"Authorization": "Bearer " + ids["token"]}).status_code == 200
    assert client.get("/v1/me", headers={"Authorization": "Bearer " + client.cookies["zw_session"]}).status_code == 401
