from uuid import uuid4

import psycopg
from test_auth import csrf
from test_modules import PASSWORD, sign_in_new_company


def open_customers(client, company: str = "Müşteri Atölyesi") -> str:
    email = sign_in_new_company(client, company)
    assert client.post("/api/v1/workspace/setup", headers=csrf(client), json={"modules": ["customers"]}).status_code == 200
    return email


def add(client, **fields) -> dict:
    response = client.post("/api/v1/customers", headers=csrf(client), json={"name": "Deniz Yapı", **fields})
    assert response.status_code == 201, response.text
    return response.json()


def test_customers_need_the_module(client) -> None:
    assert client.get("/api/v1/customers").status_code == 401

    sign_in_new_company(client)
    assert client.get("/api/v1/customers").status_code == 403
    assert client.post("/api/v1/workspace/setup", headers=csrf(client), json={"modules": ["tasks"]}).status_code == 200
    closed = client.get("/api/v1/customers")
    assert closed.status_code == 403
    assert closed.json()["detail"] == "Bu modül çalışma alanınızda açık değil."
    assert client.post("/api/v1/customers", headers=csrf(client), json={"name": "Kapalı Modül"}).status_code == 403


def test_create_update_and_delete_customer(client, database: str) -> None:
    open_customers(client)

    assert client.post("/api/v1/customers", json={"name": "CSRF Yok"}).status_code == 403
    invalid = client.post(
        "/api/v1/customers",
        headers=csrf(client),
        json={"name": "A", "email": "gecersiz", "phone": "12ab"},
    )
    assert invalid.status_code == 422
    messages = {item["loc"][-1]: item["msg"] for item in invalid.json()["detail"]}
    assert messages["name"] == "Bu alan çok kısa."
    assert messages["email"] == "Geçerli bir e-posta adresi girin."
    assert messages["phone"] == "Geçerli bir telefon numarası girin."

    created = add(client, email="Satis@Deniz.example.com", phone="+90 532 000 00 00", note="  Ana bayi  ")
    assert created["email"] == "satis@deniz.example.com"
    assert created["note"] == "Ana bayi"

    blank = add(client, name="  Ege   Mobilya ", email="", phone="")
    assert blank["name"] == "Ege Mobilya"
    assert blank["email"] is None

    duplicate = client.post("/api/v1/customers", headers=csrf(client), json={"name": "Başka", "email": "satis@deniz.example.com"})
    assert duplicate.status_code == 409
    assert duplicate.json()["detail"] == "Bu e-posta adresiyle kayıtlı bir müşteri zaten var."

    updated = client.put(
        f"/api/v1/customers/{created['id']}",
        headers=csrf(client),
        json={"name": "Deniz Yapı A.Ş.", "email": "satis@deniz.example.com", "phone": None, "note": "Ana bayi"},
    )
    assert updated.status_code == 200
    assert updated.json()["name"] == "Deniz Yapı A.Ş."
    assert updated.json()["phone"] is None

    taken = client.put(f"/api/v1/customers/{blank['id']}", headers=csrf(client), json={"name": "Ege Mobilya", "email": "SATIS@deniz.example.com"})
    assert taken.status_code == 409

    assert client.delete(f"/api/v1/customers/{created['id']}", headers=csrf(client)).status_code == 204
    assert client.get(f"/api/v1/customers/{created['id']}").status_code == 404
    assert client.delete(f"/api/v1/customers/{created['id']}", headers=csrf(client)).status_code == 404
    reused = add(client, name="Yeni Deniz", email="satis@deniz.example.com")
    assert reused["email"] == "satis@deniz.example.com"

    with psycopg.connect(database) as connection:
        kept = connection.execute("SELECT deleted_at IS NOT NULL FROM customers WHERE id = %s", (created["id"],)).fetchone()
        actions = connection.execute(
            "SELECT action, summary::text FROM audit_logs WHERE entity_id = %s ORDER BY created_at",
            (created["id"],),
        ).fetchall()
    assert kept == (True,)
    assert [action for action, _ in actions] == ["customer.created", "customer.updated", "customer.deleted"]
    assert all("deniz.example.com" not in summary for _, summary in actions)


def test_list_search_sort_and_pages(client) -> None:
    open_customers(client)
    for name in ["Çınar Lojistik", "ahmet market", "Bora Tekstil", "Zeytin 100%_Kooperatif"]:
        add(client, name=name, email=f"{uuid4().hex[:6]}@example.com")

    by_name = client.get("/api/v1/customers", params={"sort": "name"}).json()
    assert by_name["total"] == 4
    assert [item["name"] for item in by_name["items"]] == ["ahmet market", "Bora Tekstil", "Çınar Lojistik", "Zeytin 100%_Kooperatif"]

    newest = client.get("/api/v1/customers").json()["items"]
    assert newest[0]["name"] == "Zeytin 100%_Kooperatif"

    assert [item["name"] for item in client.get("/api/v1/customers", params={"q": "tekstil"}).json()["items"]] == ["Bora Tekstil"]
    assert [item["name"] for item in client.get("/api/v1/customers", params={"q": "ÇINAR"}).json()["items"]] == ["Çınar Lojistik"]
    assert [item["name"] for item in client.get("/api/v1/customers", params={"q": "çınar"}).json()["items"]] == ["Çınar Lojistik"]
    assert client.get("/api/v1/customers", params={"q": "%"}).json()["total"] == 1
    assert client.get("/api/v1/customers", params={"q": "_"}).json()["total"] == 1

    first = client.get("/api/v1/customers", params={"page_size": 3, "sort": "name"}).json()
    second = client.get("/api/v1/customers", params={"page_size": 3, "page": 2, "sort": "name"}).json()
    assert len(first["items"]) == 3
    assert len(second["items"]) == 1
    assert {item["id"] for item in first["items"]}.isdisjoint(item["id"] for item in second["items"])
    assert client.get("/api/v1/customers", params={"page_size": 500}).status_code == 422
    assert client.get("/api/v1/customers", params={"sort": "email"}).status_code == 422


def test_customers_stay_in_their_company(client) -> None:
    first = open_customers(client, "Birinci Müşteri")
    owned = add(client, name="Gizli Müşteri", email="gizli@example.com")
    assert client.post("/api/v1/auth/logout", headers=csrf(client)).status_code == 204

    open_customers(client, "İkinci Müşteri")
    assert client.get("/api/v1/customers").json()["total"] == 0
    assert client.get(f"/api/v1/customers/{owned['id']}").status_code == 404
    assert client.put(f"/api/v1/customers/{owned['id']}", headers=csrf(client), json={"name": "Ele geçirildi"}).status_code == 404
    assert client.delete(f"/api/v1/customers/{owned['id']}", headers=csrf(client)).status_code == 404
    add(client, name="Kendi Müşterim", email="gizli@example.com")
    assert client.post("/api/v1/auth/logout", headers=csrf(client)).status_code == 204

    assert client.post("/api/v1/auth/login", headers=csrf(client), json={"email": first, "password": PASSWORD}).status_code == 200
    items = client.get("/api/v1/customers").json()["items"]
    assert [item["name"] for item in items] == ["Gizli Müşteri"]
