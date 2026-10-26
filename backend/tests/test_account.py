import csv
import io
import zipfile
from uuid import uuid4

from fastapi.testclient import TestClient
from test_auth import csrf
from test_modules import PASSWORD, sign_in_new_company
from test_support import make_admin
from test_team import accept, invite


def workspace(client, name: str) -> str:
    email = sign_in_new_company(client, name)
    assert client.post("/api/v1/workspace/setup", headers=csrf(client), json={"modules": ["customers", "inventory", "tasks"]}).status_code == 200
    return email


def read_csv(bundle: zipfile.ZipFile, name: str) -> list[dict[str, str]]:
    text = bundle.read(name).decode("utf-8")
    assert text.startswith("\ufeff")
    return list(csv.DictReader(io.StringIO(text[1:]), delimiter=";"))


def test_workspace_export_is_a_zip_of_company_rows(client) -> None:
    workspace(client, "İhracat Atölyesi")
    client.post("/api/v1/customers", headers=csrf(client), json={"name": "Bora; Ltd."})
    client.post(
        "/api/v1/inventory/products",
        headers=csrf(client),
        json={"sku": f"K-{uuid4().hex[:6]}", "name": "Kil", "unit": "kg", "min_stock": "0", "initial_stock": "12.5"},
    )
    response = client.post("/api/v1/exports/workspace", headers=csrf(client))
    assert response.status_code == 200
    assert response.headers["content-type"] == "application/zip"
    assert "attachment" in response.headers["content-disposition"]
    bundle = zipfile.ZipFile(io.BytesIO(response.content))
    names = set(bundle.namelist())
    assert {"BENIOKU.txt", "musteriler.csv", "urunler.csv", "gorevler.csv", "uyeler.csv", "etkinlikler.csv"} <= names
    customers = read_csv(bundle, "musteriler.csv")
    assert [row["name"] for row in customers] == ["Bora; Ltd."]
    assert "company_id" not in customers[0]
    assert read_csv(bundle, "urunler.csv")[0]["stock_quantity"] == "12,5"
    members = read_csv(bundle, "uyeler.csv")
    assert len(members) == 1 and "password_hash" not in members[0] and members[0]["role"] == "owner"
    assert client.get("/api/v1/activity", params={"module": "workspace"}).json()["items"][0]["verb"] == "çalışma alanı verilerini indirdi"

    personal = client.get("/api/v1/me/export")
    assert personal.status_code == 200 and "attachment" in personal.headers["content-disposition"]
    data = personal.json()
    assert data["profile"]["email"] and data["memberships"][0]["company"] == "İhracat Atölyesi"
    assert "password_hash" not in data["profile"]


def test_members_cannot_export_and_can_close_their_own_account(client) -> None:
    workspace(client, "Üye Kapatma")
    email = f"uye-{uuid4().hex[:8]}@example.com"
    link = invite(client, email).json()["invite_path"]

    from app.main import create_app

    with TestClient(create_app()) as other:
        assert accept(other, link, password="uye-sifresi-2026").status_code == 201
        assert other.post("/api/v1/exports/workspace", headers=csrf(other)).status_code == 403
        assert other.post("/api/v1/workspace/closure", headers=csrf(other), json={"password": "uye-sifresi-2026"}).status_code == 403
        assert other.post("/api/v1/me/close", headers=csrf(other), json={"password": "yanlis"}).status_code == 403
        assert other.post("/api/v1/me/close", headers=csrf(other), json={"password": "uye-sifresi-2026"}).status_code == 204
        assert other.get("/api/v1/auth/me").status_code == 401
        login = other.post("/api/v1/auth/login", headers=csrf(other), json={"email": email, "password": "uye-sifresi-2026"})
        assert login.status_code in {401, 403}

    assert client.post("/api/v1/me/close", headers=csrf(client), json={"password": PASSWORD}).status_code == 409
    members = client.get("/api/v1/team").json()["members"]
    assert [m["role"] for m in members] == ["owner"]


def test_closure_request_cancel_and_admin_completion(client, database: str) -> None:
    owner_email = workspace(client, "Kapanan Atölye")
    assert client.get("/api/v1/workspace/closure").json() is None
    assert client.post("/api/v1/workspace/closure", headers=csrf(client), json={"password": "yanlis"}).status_code == 403
    opened = client.post("/api/v1/workspace/closure", headers=csrf(client), json={"password": PASSWORD, "reason": "Faaliyeti durdurduk"})
    assert opened.status_code == 201, opened.text
    assert client.post("/api/v1/workspace/closure", headers=csrf(client), json={"password": PASSWORD}).status_code == 409
    assert client.get("/api/v1/auth/me").json()["closure_scheduled_for"] == opened.json()["scheduled_for"]
    assert client.delete("/api/v1/workspace/closure", headers=csrf(client)).status_code == 204
    assert client.get("/api/v1/auth/me").json()["closure_scheduled_for"] is None
    request = client.post("/api/v1/workspace/closure", headers=csrf(client), json={"password": PASSWORD}).json()

    from app.main import create_app

    with TestClient(create_app()) as staff:
        admin_email = workspace(staff, "LUMINOVA Kapatma Ekibi")
        assert staff.get("/api/v1/admin/closures").status_code == 403
        make_admin(database, admin_email)
        pending = [row for row in staff.get("/api/v1/admin/closures").json() if row["id"] == request["id"]]
        assert pending and pending[0]["company_name"] == "Kapanan Atölye" and pending[0]["due"] is False
        assert staff.get("/api/v1/admin/overview").json()["pending_closures"] >= 1
        assert staff.post(f"/api/v1/admin/closures/{request['id']}/complete", headers=csrf(staff)).status_code == 204
        assert staff.post(f"/api/v1/admin/closures/{request['id']}/complete", headers=csrf(staff)).status_code == 404

    assert client.get("/api/v1/auth/me").status_code == 401
    login = client.post("/api/v1/auth/login", headers=csrf(client), json={"email": owner_email, "password": PASSWORD})
    assert login.status_code == 403
