from uuid import uuid4

import psycopg
from fastapi.testclient import TestClient
from test_auth import csrf
from test_mail import TEST_DSN
from test_modules import sign_in_new_company
from test_team import accept, invite

STAFF_PASSWORD = "Yonetim-Test-Sifresi-2026"


def staff_client() -> TestClient:
    from app.cli import create_admin
    from app.main import create_app

    login = f"staff-{uuid4().hex[:6]}"
    assert create_admin(login, STAFF_PASSWORD) == 0
    staff = TestClient(create_app())
    staff.__enter__()
    response = staff.post("/api/v1/auth/login", headers=csrf(staff), json={"email": login, "password": STAFF_PASSWORD})
    assert response.status_code == 200, response.text
    return staff


def busy_company(client, name: str) -> str:
    sign_in_new_company(client, name)
    modules = ["customers", "sales", "inventory", "finance", "tasks", "projects"]
    assert client.post("/api/v1/workspace/setup", headers=csrf(client), json={"modules": modules}).status_code == 200
    buyer = client.post("/api/v1/customers", headers=csrf(client), json={"name": "Gizli Müşteri A.Ş."}).json()["id"]
    client.post("/api/v1/inventory/products", headers=csrf(client), json={"sku": f"P-{uuid4().hex[:5]}", "name": "Gizli Ürün", "unit": "adet", "min_stock": "2", "initial_stock": "1"})
    client.post(
        "/api/v1/finance/records",
        headers=csrf(client),
        json={"kind": "income", "category": "Satış", "description": "Gizli gelir", "amount": "999", "record_date": "2026-10-01", "customer_id": buyer},
    )
    client.post("/api/v1/tasks", headers=csrf(client), json={"title": "Gizli görev"})
    client.post("/api/v1/projects", headers=csrf(client), json={"name": "Gizli proje"})
    return client.get("/api/v1/auth/me").json()["company_id"]


def test_staff_account_sees_companies_but_no_business_data(client) -> None:
    company_id = busy_company(client, f"Panel Atölyesi {uuid4().hex[:4]}")
    from app.main import create_app

    with TestClient(create_app()) as other:
        assert accept(other, invite(client, f"ekip-{uuid4().hex[:6]}@example.com").json()["invite_path"]).status_code == 201

    assert client.get("/api/v1/admin/overview").status_code == 403
    staff = staff_client()
    try:
        me = staff.get("/api/v1/auth/me").json()
        assert me["staff_only"] is True and me["company_id"] is None
        assert staff.get("/api/v1/tasks").status_code == 401

        detail = staff.get(f"/api/v1/admin/companies/{company_id}")
        assert detail.status_code == 200
        body = detail.json()
        assert {item["key"] for item in body["module_list"]} >= {"finance", "customers", "tasks"}
        assert [person["role"] for person in body["people"]] == ["owner", "member"]
        assert "Gizli" not in detail.text

        sent = staff.post(f"/api/v1/admin/companies/{company_id}/messages", headers=csrf(staff), json={"subject": "Bakım duyurusu", "body": "Cumartesi 02:00'de kısa bakım var."})
        assert sent.status_code == 201 and sent.json()["category"] == "notice"
        notes = [item for item in client.get("/api/v1/notifications").json()["items"] if item["category"] == "support"]
        assert notes[0]["title"] == "LUMINOVA Destek size mesaj gönderdi: Bakım duyurusu"
        ticket = client.get("/api/v1/support/tickets").json()["items"][0]
        assert ticket["opened_by_staff"] is True and ticket["created_by_name"] == "LUMINOVA Destek"
        replied = client.post(f"/api/v1/support/tickets/{ticket['id']}/messages", headers=csrf(client), json={"body": "Teşekkürler, haberimiz var."})
        assert replied.status_code == 200
        assert staff.get(f"/api/v1/admin/support/tickets/{ticket['id']}").json()["status"] == "open"
    finally:
        staff.__exit__(None, None, None)


def test_company_deletion_removes_every_row(client) -> None:
    name = f"Silinecek Atölye {uuid4().hex[:4]}"
    company_id = busy_company(client, name)
    owner_email = client.get("/api/v1/auth/me").json()["email"]
    staff = staff_client()
    try:
        assert staff.request("DELETE", f"/api/v1/admin/companies/{company_id}", headers=csrf(staff), json={"confirm_name": "yanlış"}).status_code == 422
        assert staff.request("DELETE", f"/api/v1/admin/companies/{company_id}", headers=csrf(staff), json={"confirm_name": name}).status_code == 204
        assert staff.get(f"/api/v1/admin/companies/{company_id}").status_code == 404
    finally:
        staff.__exit__(None, None, None)

    with psycopg.connect(TEST_DSN) as connection:
        tables = [row[0] for row in connection.execute("SELECT table_name FROM information_schema.columns WHERE column_name = 'company_id' AND table_schema = 'public'")]
        leftovers = {table: connection.execute(f'SELECT count(*) FROM "{table}" WHERE company_id = %s', (company_id,)).fetchone()[0] for table in tables}
        assert {table: count for table, count in leftovers.items() if count} == {}
        assert connection.execute("SELECT count(*) FROM users WHERE email = %s", (owner_email,)).fetchone()[0] == 0
    assert client.get("/api/v1/auth/me").status_code == 401
