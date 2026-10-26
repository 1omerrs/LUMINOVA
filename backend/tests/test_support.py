from uuid import uuid4

import psycopg
from fastapi.testclient import TestClient
from test_auth import csrf
from test_modules import sign_in_new_company
from test_team import accept, invite


def workspace(client, name: str) -> str:
    email = sign_in_new_company(client, name)
    assert client.post("/api/v1/workspace/setup", headers=csrf(client), json={"modules": ["tasks"]}).status_code == 200
    return email


def make_admin(database: str, email: str) -> None:
    with psycopg.connect(database) as connection:
        connection.execute("UPDATE users SET is_platform_admin = true WHERE email = %s", (email,))


def open_ticket(client, subject: str = "Stok raporu açılmıyor", body: str = "Rapor sayfası boş görünüyor."):
    return client.post("/api/v1/support/tickets", headers=csrf(client), json={"subject": subject, "category": "bug", "body": body})


def test_ticket_thread_and_staff_reply(client, database: str) -> None:
    workspace(client, "Destek Atölyesi")
    assert client.post("/api/v1/support/tickets", headers=csrf(client), json={"subject": "  ", "category": "bug", "body": "x"}).status_code == 422
    assert client.post("/api/v1/support/tickets", headers=csrf(client), json={"subject": "Konu", "category": "billing", "body": "x"}).status_code == 422
    created = open_ticket(client)
    assert created.status_code == 201, created.text
    ticket = created.json()
    assert ticket["code"] == "DT-0001" and ticket["status"] == "open" and ticket["message_count"] == 1
    assert ticket["company_name"] is None
    assert client.get("/api/v1/admin/overview").status_code == 403

    followed = client.post(f"/api/v1/support/tickets/{ticket['id']}/messages", headers=csrf(client), json={"body": "Ekran görüntüsü ekleyemedim."}).json()
    assert [m["author_kind"] for m in followed["messages"]] == ["customer", "customer"]

    from app.main import create_app

    with TestClient(create_app()) as staff:
        admin_email = workspace(staff, "LUMINOVA Ekibi")
        make_admin(database, admin_email)
        assert staff.get("/api/v1/auth/me").json()["is_platform_admin"] is True
        queue = staff.get("/api/v1/admin/support/tickets", params={"status": "open"}).json()
        mine = next(item for item in queue["items"] if item["id"] == ticket["id"])
        assert mine["company_name"] == "Destek Atölyesi" and mine["message_count"] == 2
        assert staff.get(f"/api/v1/support/tickets/{ticket['id']}").status_code == 404

        answered = staff.post(f"/api/v1/admin/support/tickets/{ticket['id']}/reply", headers=csrf(staff), json={"body": "Düzeltme yayında, sayfayı yenileyin."}).json()
        assert answered["status"] == "answered"
        assert answered["messages"][-1]["author_name"].startswith("LUMINOVA Destek · ")
        overview = staff.get("/api/v1/admin/overview").json()
        assert overview["companies"] >= 2 and overview["answered_tickets"] >= 1
        listed = staff.get("/api/v1/admin/companies", params={"q": "Destek Atölyesi"}).json()
        assert listed["items"][0]["open_tickets"] == 0 and listed["items"][0]["members"] == 1

    seen = client.get(f"/api/v1/support/tickets/{ticket['id']}").json()
    assert seen["status"] == "answered" and seen["messages"][-1]["author_name"] == "LUMINOVA Destek"
    notes = [item for item in client.get("/api/v1/notifications").json()["items"] if item["category"] == "support"]
    assert notes[0]["title"] == "DT-0001 talebinize yanıt geldi." and notes[0]["link"].endswith(ticket["id"])

    closed = client.post(f"/api/v1/support/tickets/{ticket['id']}/close", headers=csrf(client)).json()
    assert closed["status"] == "closed" and closed["can_reply"] is False
    assert client.post(f"/api/v1/support/tickets/{ticket['id']}/messages", headers=csrf(client), json={"body": "Bir şey daha"}).status_code == 409
    summary = client.get("/api/v1/support/tickets").json()
    assert summary["closed"] == 1 and summary["open"] == 0
    activity = [item["verb"] for item in client.get("/api/v1/activity", params={"module": "workspace"}).json()["items"]]
    assert activity[:3] == ["destek talebini kapattı", "destek talebine yazdı", "destek talebi açtı"]


def test_members_see_only_their_own_tickets(client) -> None:
    workspace(client, "Talep Ekibi")
    owner_ticket = open_ticket(client, subject="Sahibin talebi").json()
    created = invite(client, f"uye-{uuid4().hex[:8]}@example.com").json()

    from app.main import create_app

    with TestClient(create_app()) as other:
        assert accept(other, created["invite_path"]).status_code == 201
        assert other.get("/api/v1/support/tickets").json()["items"] == []
        assert other.get(f"/api/v1/support/tickets/{owner_ticket['id']}").status_code == 404
        member_ticket = open_ticket(other, subject="Üyenin talebi").json()
        assert member_ticket["code"] == "DT-0002"
        assert [item["subject"] for item in other.get("/api/v1/support/tickets").json()["items"]] == ["Üyenin talebi"]
        assert not any("destek" in item["verb"] for item in other.get("/api/v1/activity").json()["items"])

    assert sorted(item["subject"] for item in client.get("/api/v1/support/tickets").json()["items"]) == ["Sahibin talebi", "Üyenin talebi"]
