def test_production_approval_routes_fail_closed_without_api_token(client, monkeypatch):
    monkeypatch.setenv("APP_ENV", "production")
    monkeypatch.delenv("API_TOKEN", raising=False)

    response = client.get("/tasks/1/webflow-proposals")

    assert response.status_code == 503
    assert "API_TOKEN" in response.json()["detail"]


def test_approval_routes_fail_closed_by_default_without_api_token(client, monkeypatch):
    monkeypatch.delenv("APP_ENV", raising=False)
    monkeypatch.delenv("API_TOKEN", raising=False)

    response = client.get("/tasks/1/webflow-proposals")

    assert response.status_code == 503
