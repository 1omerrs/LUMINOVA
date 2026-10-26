from uuid import uuid4

from fastapi.testclient import TestClient
from test_auth import csrf
from test_modules import sign_in_new_company

PASSWORD = "katilim-sifresi-2026"


def owner_workspace(client, name: str) -> str:
    sign_in_new_company(client, name)
    assert client.post("/api/v1/workspace/setup", headers=csrf(client), json={"modules": ["tasks", "inventory"]}).status_code == 200
    return client.get("/api/v1/team").json()["join_code"]


def sign_up(visitor, code: str, email: str, **extra):
    body = {"first_name": "Deniz", "last_name": "Aday", "email": email, "password": PASSWORD, "join_code": code, **extra}
    return visitor.post("/api/v1/auth/register/member", headers=csrf(visitor), json=body)


def login(visitor, email: str):
    return visitor.post("/api/v1/auth/login", headers=csrf(visitor), json={"email": email, "password": PASSWORD})


def test_join_code_sign_up_waits_for_approval(client) -> None:
    code = owner_workspace(client, "Kodlu Atölye")
    assert len(code) == 9 and code[4] == "-"
    from app.main import create_app

    with TestClient(create_app()) as visitor:
        assert visitor.get("/api/v1/auth/join/preview", params={"code": code.replace("-", "").lower()}).json() == {"company_name": "Kodlu Atölye"}
        assert visitor.get("/api/v1/auth/join/preview", params={"code": "AAAA-AAAA"}).status_code == 404
        assert sign_up(visitor, "AAAA-AAAA", "yok@example.com").status_code == 404

        email = f"aday-{uuid4().hex[:8]}@example.com"
        created = sign_up(visitor, code, email, position="Montaj ustası", note="Pazartesi başlıyorum.")
        assert created.status_code == 201, created.text
        assert "yöneticisi isteğinizi onaylayınca" in created.json()["message"]
        assert login(visitor, email).json()["detail"] == "E-posta adresini doğrulamanız gerekiyor."

        listed = client.get("/api/v1/team").json()["join_requests"]
        assert listed[0]["email"] == email and listed[0]["position"] == "Montaj ustası" and listed[0]["email_verified"] is False
        assert client.post(f"/api/v1/team/join-requests/{listed[0]['id']}/approve", headers=csrf(client), json={}).status_code == 409

        token = created.json()["verification_path"].split("token=", 1)[1]
        assert visitor.post("/api/v1/auth/verify-email", headers=csrf(visitor), json={"token": token}).status_code == 200
        waiting = login(visitor, email)
        assert waiting.status_code == 403 and "Kodlu Atölye yöneticisinin onayını bekliyor" in waiting.json()["detail"]
        titles = [item["title"] for item in client.get("/api/v1/notifications").json()["items"] if item["category"] == "team"]
        assert "Deniz Aday ekibe katılmak istiyor." in titles

        approved = client.post(f"/api/v1/team/join-requests/{listed[0]['id']}/approve", headers=csrf(client), json={"permissions": {"tasks": "edit"}})
        assert approved.status_code == 200 and approved.json()["join_requests"] == []
        person = next(item for item in approved.json()["members"] if item["email"] == email)
        assert person["role"] == "member" and person["permissions"] == {"tasks": "edit"}

        assert login(visitor, email).status_code == 200
        modules = {item["key"] for item in visitor.get("/api/v1/modules").json()["modules"] if item["enabled"]}
        assert modules == {"tasks"}
        assert visitor.post(f"/api/v1/team/join-requests/{listed[0]['id']}/reject", headers=csrf(visitor)).status_code == 403


def test_password_reset_requests_are_throttled(client) -> None:
    import psycopg

    from test_mail import TEST_DSN

    sign_in_new_company(client, "Sınırlı Atölye")
    email = client.get("/api/v1/auth/me").json()["email"]
    replies = {client.post("/api/v1/auth/forgot-password", headers=csrf(client), json={"email": email}).json()["message"] for _ in range(5)}
    assert len(replies) == 1
    with psycopg.connect(TEST_DSN) as connection:
        count = connection.execute(
            "SELECT count(*) FROM password_reset_tokens t JOIN users u ON u.id = t.user_id WHERE u.email = %s", (email,)
        ).fetchone()[0]
    assert count == 3


def test_rejected_and_renewed_codes(client) -> None:
    code = owner_workspace(client, "Kapalı Kapı")
    from app.main import create_app

    with TestClient(create_app()) as visitor:
        email = f"red-{uuid4().hex[:8]}@example.com"
        created = sign_up(visitor, code, email).json()
        visitor.post("/api/v1/auth/verify-email", headers=csrf(visitor), json={"token": created["verification_path"].split("token=", 1)[1]})
        request_id = client.get("/api/v1/team").json()["join_requests"][0]["id"]
        assert client.post(f"/api/v1/team/join-requests/{request_id}/reject", headers=csrf(client)).status_code == 200
        assert "onaylanmadı" in login(visitor, email).json()["detail"]
        assert client.post(f"/api/v1/team/join-requests/{request_id}/approve", headers=csrf(client), json={}).status_code == 404

        renewed = client.post("/api/v1/team/join-code", headers=csrf(client)).json()["join_code"]
        assert renewed != code
        assert visitor.get("/api/v1/auth/join/preview", params={"code": code}).status_code == 404
        assert visitor.get("/api/v1/auth/join/preview", params={"code": renewed}).status_code == 200
