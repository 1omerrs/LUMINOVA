from fastapi.testclient import TestClient

from app.main import create_app


def test_unhandled_exception_hides_internal_details() -> None:
    app = create_app()

    @app.get("/api/v1/_boom")
    def boom() -> None:
        raise RuntimeError("session-token-super-secret")

    with TestClient(app, raise_server_exceptions=False) as client:
        response = client.get("/api/v1/_boom")

    assert response.status_code == 500
    assert response.json()["detail"] == "Beklenmeyen bir hata oluştu."
    assert "session-token-super-secret" not in response.text
    assert "traceback" not in response.text.lower()
