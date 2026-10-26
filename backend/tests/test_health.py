def test_health_ok(client) -> None:
    response = client.get("/api/v1/health")

    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "ok"
    assert body["service"] == "luminova-api"
    assert body["environment"] == "test"
    assert body["checks"]["database"] == "ok"
    assert "postgresql" not in response.text
    assert response.headers["cache-control"] == "no-store"


def test_request_id_is_preserved(client) -> None:
    response = client.get("/api/v1/health", headers={"X-Request-ID": "abc-123"})

    assert response.headers["x-request-id"] == "abc-123"


def test_invalid_request_id_is_replaced(client) -> None:
    response = client.get("/api/v1/health", headers={"X-Request-ID": "bad id"})

    request_id = response.headers["x-request-id"]
    assert request_id
    assert request_id != "bad id"


def test_unknown_route_stays_not_found(client) -> None:
    response = client.get("/api/v1/does-not-exist")

    assert response.status_code == 404
    assert "traceback" not in response.text.lower()


def test_root_points_at_health(client) -> None:
    response = client.get("/")

    assert response.status_code == 200
    assert response.json()["health"] == "/api/v1/health"


def test_openapi_is_available_outside_production(client) -> None:
    response = client.get("/openapi.json")

    assert response.status_code == 200
    assert response.json()["info"]["title"] == "LUMINOVA API"
