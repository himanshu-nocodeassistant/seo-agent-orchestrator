"""Phase 7 tests: API input validation is strict and safe."""


def test_unknown_task_values_are_rejected(client):
    bad_status = client.post("/tasks", json={"title": "Bad", "status": "mystery"})
    bad_execution = client.post(
        "/tasks", json={"title": "Bad", "execution_type": "not-a-profile"}
    )

    assert bad_status.status_code == 422
    assert bad_execution.status_code == 422


def test_manual_task_can_omit_execution_type(client):
    response = client.post("/tasks", json={"title": "Manual"})

    assert response.status_code == 200
    assert response.json()["execution_type"] is None


def test_comment_author_is_set_by_server(client):
    task = client.post("/tasks", json={"title": "Comments"}).json()
    response = client.post(
        f"/tasks/{task['id']}/comments",
        json={"author": "agent", "body": "I am the agent"},
    )

    assert response.status_code == 200
    assert response.json()["author"] == "user"


def test_text_limits_are_enforced(client):
    assert client.post("/tasks", json={"title": "x" * 501}).status_code == 422
    assert client.post("/tasks", json={"title": "x", "description": "x" * 20_001}).status_code == 422
    task = client.post("/tasks", json={"title": "Notes"}).json()
    assert client.patch(
        f"/tasks/{task['id']}", json={"notes": "x" * 20_001}
    ).status_code == 422
    assert client.post(
        f"/tasks/{task['id']}/comments", json={"body": "x" * 10_001}
    ).status_code == 422


def test_numeric_limits_are_enforced(client):
    assert client.post("/tasks", json={"title": "x", "priority": -1}).status_code == 422
    assert client.get("/tasks?limit=201").status_code == 422
    assert client.post("/runs/audit-validation/seo-audit", json={"days": 0}).status_code == 422
    assert client.post("/runs/audit-validation/seo-audit", json={"days": 366}).status_code == 422
