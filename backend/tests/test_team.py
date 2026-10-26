from uuid import uuid4

from fastapi.testclient import TestClient
from test_auth import csrf
from test_modules import sign_in_new_company


def open_workspace(client, company: str = "Ekip Atölyesi") -> str:
    email = sign_in_new_company(client, company)
    assert client.post("/api/v1/workspace/setup", headers=csrf(client), json={"modules": ["tasks"]}).status_code == 200
    return email


def invite(client, email: str, role: str = "member", permissions: dict[str, str] | None = None):
    """Members get edit access to every enabled module unless the test passes its own permissions."""
    if permissions is None and role == "member":
        permissions = {item["key"]: "edit" for item in client.get("/api/v1/team").json().get("grantable", [])}
    body = {"email": email, "role": role, **({"permissions": permissions} if permissions is not None else {})}
    return client.post("/api/v1/team/invitations", headers=csrf(client), json=body)


def accept(other: TestClient, path: str, first: str = "Ece", last: str = "Yıldız", password: str = "ekip-sifresi-2026"):
    token = path.split("token=", 1)[1]
    return other.post("/api/v1/auth/invitations/accept", headers=csrf(other), json={"token": token, "first_name": first, "last_name": last, "password": password})


def test_invite_accept_and_roles(client, database: str) -> None:
    owner_email = open_workspace(client)
    assert invite(client, owner_email).status_code == 409

    ece_email = f"ece-{uuid4().hex[:8]}@example.com"
    created = invite(client, f"  {ece_email.upper()} ")
    assert created.status_code == 201, created.text
    body = created.json()
    assert body["email_sent"] is False
    assert body["invite_path"].startswith("/davet?token=")
    assert body["invitation"]["email"] == ece_email
    assert invite(client, ece_email).json()["detail"] == "Bu e-posta adresine gönderilmiş açık bir davet zaten var."
    assert len(client.get("/api/v1/team").json()["invitations"]) == 1

    from app.main import create_app

    with TestClient(create_app()) as other:
        token = body["invite_path"].split("token=", 1)[1]
        preview = other.get("/api/v1/auth/invitations/preview", params={"token": token}).json()
        assert preview["company_name"] == "Ekip Atölyesi" and preview["role"] == "member"
        assert accept(other, body["invite_path"], password="short").status_code == 422
        joined = accept(other, body["invite_path"])
        assert joined.status_code == 201, joined.text
        assert joined.json()["role"] == "member" and joined.json()["company_name"] == "Ekip Atölyesi"
        assert other.get("/api/v1/tasks").status_code == 200
        assert accept(other, body["invite_path"]).status_code == 400

        assert other.put("/api/v1/modules", headers=csrf(other), json={"modules": ["tasks", "finance"]}).status_code == 403
        assert invite(other, "baska@example.com").status_code == 403
        listed = other.get("/api/v1/team").json()
        assert listed["can_manage"] is False and listed["invitations"] == []
        assert [m["role"] for m in listed["members"]] == ["owner", "member"]
        ece = next(m for m in listed["members"] if m["me"])

        assignees = other.get("/api/v1/tasks/assignees").json()
        assert len(assignees) == 2

        notes = [item for item in client.get("/api/v1/notifications").json()["items"] if item["category"] == "team"]
        assert notes and notes[0]["title"] == "Ece Yıldız ekibe katıldı."

        promoted = client.put(f"/api/v1/team/members/{ece['user_id']}", headers=csrf(client), json={"role": "admin"}).json()
        assert next(m for m in promoted["members"] if m["user_id"] == ece["user_id"])["role"] == "admin"
        assert other.get("/api/v1/team").json()["can_manage"] is True
        assert invite(other, "yonetici@example.com", role="admin").status_code == 403
        assert invite(other, f"uye-{uuid4().hex[:8]}@example.com").status_code == 201
        owner_id = next(m for m in promoted["members"] if m["role"] == "owner")["user_id"]
        assert other.delete(f"/api/v1/team/members/{owner_id}", headers=csrf(other)).status_code == 409
        assert other.put(f"/api/v1/team/members/{owner_id}", headers=csrf(other), json={"role": "member"}).status_code == 403

        assert client.delete(f"/api/v1/team/members/{ece['user_id']}", headers=csrf(client)).status_code == 200
        assert other.get("/api/v1/team").status_code == 401
        login = other.post("/api/v1/auth/login", headers=csrf(other), json={"email": ece_email, "password": "ekip-sifresi-2026"})
        assert login.status_code == 403
        assert login.json()["detail"].startswith("Bu hesabın etkin bir çalışma alanı üyeliği yok.")


def test_revoked_invitation_and_tenancy(client) -> None:
    open_workspace(client, "Birinci Ekip")
    created = invite(client, f"iptal-{uuid4().hex[:8]}@example.com").json()
    invitations = client.get("/api/v1/team").json()["invitations"]
    assert client.delete(f"/api/v1/team/invitations/{invitations[0]['id']}", headers=csrf(client)).status_code == 204
    assert client.get("/api/v1/team").json()["invitations"] == []
    assert client.post("/api/v1/auth/logout", headers=csrf(client)).status_code == 204

    token = created["invite_path"].split("token=", 1)[1]
    assert client.get("/api/v1/auth/invitations/preview", params={"token": token}).status_code == 400
    assert accept(client, created["invite_path"]).status_code == 400

    open_workspace(client, "İkinci Ekip")
    assert client.delete(f"/api/v1/team/invitations/{invitations[0]['id']}", headers=csrf(client)).status_code == 404
    assert len(client.get("/api/v1/team").json()["members"]) == 1
